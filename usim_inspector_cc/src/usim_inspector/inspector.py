"""검수 흐름 오케스트레이션.

CheckResult: 단일 배치 검수 결과 데이터 클래스.
Inspector: 한 배치 폴더에 대해 1~9단계 검수를 실행하는 클래스.
"""

import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .iccid import IccidParser, IccidFields
from .checkfile import parse_check_file, find_log_folder, find_check_file
from .media import ocr_image, extract_video_frames
from .tools import tools


@dataclass
class CheckResult:
    """단일 배치 검수 결과."""
    batch_path: str
    batch_name: str = ""
    status: str = "PENDING"          # PASS / FAIL / ERROR
    stop_reason: str = ""

    steps: list = field(default_factory=list)  # 단계별 로그

    # 체크파일 정보
    check_file: str = ""
    total_rows: int = 0

    # ICCID 분석
    operator_code: str = ""
    operator_name: str = ""
    model_code: str = ""
    model_name: str = ""
    first_serial: str = ""
    last_serial: str = ""
    first_iccid: str = ""
    last_iccid: str = ""

    # 위반 사항
    consistency_violations: list = field(default_factory=list)
    range_violations: list = field(default_factory=list)

    # 미디어 검토
    media_files: list = field(default_factory=list)
    media_violations: list = field(default_factory=list)

    def log(self, msg: str, level: str = "INFO") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.steps.append({"time": ts, "level": level, "msg": msg})
        print(f"[{ts}] [{level}] {msg}")


class Inspector:
    """검수 규칙(rules)을 받아 배치 단위로 검수를 실행."""

    def __init__(self, rules: dict) -> None:
        self.rules = rules
        self.iccid_parser = IccidParser.from_config(rules['iccid'])
        self.known_operators = rules.get('known_operators', {})
        self.known_models = rules.get('known_models', {})

    # ---------- 단계 4~6: 체크파일 분석 ----------
    def _validate_consistency(self, data: List[IccidFields],
                              result: CheckResult) -> None:
        cfg = self.rules['validations'].get('consistency_check', {})
        if not cfg.get('enabled', True):
            return

        ref = data[0]
        result.operator_code = ref.operator
        result.model_code = ref.model
        result.operator_name = self.known_operators.get(ref.operator, "-")
        result.model_name = self.known_models.get(ref.model, "-")

        fields_to_check = cfg.get('check_fields', ['operator', 'model'])
        for row in data:
            mismatches = []
            for fld in fields_to_check:
                if getattr(row, fld) != getattr(ref, fld):
                    mismatches.append(f"{fld}={getattr(row, fld)}")
            if mismatches:
                result.consistency_violations.append({
                    "row": row.row,
                    "iccid": row.iccid,
                    "detail": ", ".join(mismatches),
                })

        if result.consistency_violations:
            result.log(f"⚠️ 사업자/모델 불일치 "
                       f"{len(result.consistency_violations)}건", "WARN")
        else:
            result.log("✅ 모든 행 사업자/모델 동일")

    def _find_serial_range(self, data: List[IccidFields],
                           result: CheckResult) -> None:
        result.first_iccid = data[0].iccid
        result.last_iccid = data[-1].iccid
        result.first_serial = data[0].serial
        result.last_serial = data[-1].serial
        result.log(f"시작카드번호: {result.first_serial} / "
                   f"마지막카드번호: {result.last_serial}")

    def _validate_serial_range(self, data: List[IccidFields],
                               result: CheckResult) -> None:
        cfg = self.rules['validations'].get('serial_range_check', {})
        if not cfg.get('enabled', True):
            return
        try:
            lo, hi = int(result.first_serial), int(result.last_serial)
            lo, hi = min(lo, hi), max(lo, hi)
        except ValueError:
            result.log("시리얼이 숫자가 아니어서 범위 검증 불가", "WARN")
            return

        for row in data:
            try:
                s = int(row.serial)
                if not (lo <= s <= hi):
                    result.range_violations.append({
                        "row": row.row, "iccid": row.iccid,
                        "serial": row.serial,
                    })
            except ValueError:
                result.range_violations.append({
                    "row": row.row, "iccid": row.iccid,
                    "serial": row.serial,
                })

        if result.range_violations:
            result.log(f"⚠️ 시리얼 범위 위반 "
                       f"{len(result.range_violations)}건", "WARN")
        else:
            result.log("✅ 모든 행 시리얼 범위 내")

    # ---------- 단계 9: 미디어 검토 ----------
    def _inspect_media(self, batch_path: Path, result: CheckResult) -> None:
        cfg = self.rules['validations'].get('media_iccid_check', {})
        if not cfg.get('enabled', True):
            return

        missing = tools().missing()
        if missing:
            result.log(
                f"⚠️ 외부 도구 일부 없음: {', '.join(missing)} → "
                f"OCR 정확도 낮을 수 있음 (README 참조)", "WARN"
            )

        img_exts = {e.lower() for e in cfg.get('image_extensions', [])}
        vid_exts = {e.lower() for e in cfg.get('video_extensions', [])}
        fps = cfg.get('video_fps_sample', 2)

        try:
            lo = int(result.first_serial)
            hi = int(result.last_serial)
            lo, hi = min(lo, hi), max(lo, hi)
        except ValueError:
            result.log("시리얼 범위 정수 변환 실패 → 미디어 검토 스킵", "WARN")
            return

        for f in sorted(batch_path.iterdir()):
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            if ext in img_exts:
                self._inspect_image_file(f, lo, hi, result)
            elif ext in vid_exts:
                self._inspect_video_file(f, lo, hi, fps, result)

    def _classify_iccids(self, iccids: list, lo: int, hi: int) -> list:
        """ICCID 리스트 중 범위 위반인 것만 반환."""
        violations = []
        for ic in iccids:
            p = self.iccid_parser.parse(ic)
            if p is None:
                continue
            try:
                s = int(p.serial)
                if not (lo <= s <= hi):
                    violations.append(ic)
            except ValueError:
                violations.append(ic)
        return violations

    def _get_op_model_hint(self, confirmed: list) -> Optional[str]:
        """확인된 ICCID에서 사업자+모델코드(11자)를 추출.
        확인된 ICCID가 없으면 known_models의 첫 번째 항목으로 대체."""
        mdl_end = self.iccid_parser.mdl_slice.stop  # 0-based exclusive (예: 11)
        for iccid in confirmed:
            return iccid[:mdl_end]
        for model_code in self.known_models:
            return self.iccid_parser.prefix + model_code
        return None

    def _inspect_image_file(self, img: Path, lo: int, hi: int,
                            result: CheckResult) -> None:
        text = ocr_image(str(img))
        confirmed = list(set(self.iccid_parser.extract_all(text)))

        # 사업자+모델코드 유추로 부분 인식 ICCID 복원
        inferred = []
        op_model = self._get_op_model_hint(confirmed)
        if op_model:
            raw = self.iccid_parser.infer_from_partial(
                text, op_model, confirmed=set(confirmed)
            )
            # 알려진 모델코드와 일치하는 것만 통과 (오탐 방지)
            inferred = [
                (ic, serial) for ic, serial in raw
                if not self.known_models or (
                    self.iccid_parser.parse(ic) is not None and
                    self.iccid_parser.parse(ic).model in self.known_models
                )
            ]

        # 위반 검사는 확인된 ICCID만 대상
        # (추정 ICCID는 시리얼 확정 불가이므로 위반 자동 판정 제외)
        violations = self._classify_iccids(confirmed, lo, hi)

        entry = {
            "name": img.name, "type": "image",
            "iccids_found": confirmed,
            "violations": violations,
            "status": "OK" if not violations else "NG",
        }
        if inferred:
            entry["iccids_inferred"] = [ic for ic, _ in inferred]
            entry["inferred_note"] = (
                "⚠️ 사업자/모델코드를 추정하여 인식했습니다. "
                "이미지를 직접 열어 시리얼번호를 확인하세요."
            )

        result.media_files.append(entry)
        for v in violations:
            result.media_violations.append({"file": img.name, "iccid": v})

        inf_note = f", 추정 {len(inferred)}개" if inferred else ""
        result.log(f"  📷 {img.name}: ICCID {len(confirmed)}개 확인{inf_note}, "
                   f"위반 {len(violations)}건")
        for ic in confirmed:
            result.log(f"    ✅ 확인: {ic}")
        for ic, serial in inferred:
            result.log(
                f"    ⚠️ 추정: {ic}  (시리얼 '{serial}' — 이미지 직접 확인 권고)",
                "WARN"
            )

    def _inspect_video_file(self, vid: Path, lo: int, hi: int,
                            fps: float, result: CheckResult) -> None:
        if not tools().ffmpeg:
            result.log(f"  🎬 {vid.name}: ffmpeg 없음 → 동영상 스킵", "WARN")
            return

        frames = extract_video_frames(vid, fps)
        confirmed_all: set = set()
        inferred_all: list = []

        for frame in frames:
            text = ocr_image(str(frame))
            frame_confirmed = list(set(self.iccid_parser.extract_all(text)))
            confirmed_all.update(frame_confirmed)
            op_model = self._get_op_model_hint(list(confirmed_all))
            if op_model:
                raw = self.iccid_parser.infer_from_partial(
                    text, op_model, confirmed=confirmed_all
                )
                for ic, serial in raw:
                    if self.known_models and (
                        self.iccid_parser.parse(ic) is None or
                        self.iccid_parser.parse(ic).model not in self.known_models
                    ):
                        continue
                    inferred_all.append((ic, serial))
                    confirmed_all.add(ic)

        # 임시 프레임 폴더 정리
        if frames:
            try:
                shutil.rmtree(frames[0].parent, ignore_errors=True)
            except Exception:
                pass

        inferred_dedup = list({ic: s for ic, s in inferred_all}.items())
        confirmed_list = list(confirmed_all - {ic for ic, _ in inferred_dedup})
        # 위반 검사는 확인된 ICCID만 대상
        violations = self._classify_iccids(confirmed_list, lo, hi)

        entry = {
            "name": vid.name, "type": "video",
            "iccids_found": sorted(confirmed_list),
            "violations": violations,
            "status": "OK" if not violations else "NG",
        }
        if inferred_dedup:
            entry["iccids_inferred"] = [ic for ic, _ in inferred_dedup]
            entry["inferred_note"] = (
                "⚠️ 사업자/모델코드를 추정하여 인식했습니다. "
                "동영상을 직접 열어 시리얼번호를 확인하세요."
            )

        result.media_files.append(entry)
        for v in violations:
            result.media_violations.append({"file": vid.name, "iccid": v})

        inf_note = f", 추정 {len(inferred_dedup)}개" if inferred_dedup else ""
        result.log(f"  🎬 {vid.name}: ICCID {len(confirmed_list)}개 확인{inf_note}, "
                   f"위반 {len(violations)}건")
        for ic, serial in inferred_dedup:
            result.log(
                f"    ⚠️ 추정 ICCID: {ic}  (시리얼 '{serial}' OCR 인식 — "
                f"동영상 직접 확인 권고)", "WARN"
            )

    # ---------- 메인 ----------
    def inspect_batch(self, batch_path: Path) -> CheckResult:
        """배치 폴더 하나를 검수하고 결과 반환."""
        result = CheckResult(batch_path=str(batch_path),
                             batch_name=batch_path.name)
        result.log(f"===== 배치 검수 시작: {batch_path.name} =====")

        # 1. 경로 존재 확인
        if not batch_path.exists() or not any(batch_path.iterdir()):
            result.status = "ERROR"
            result.stop_reason = "경로가 없거나 비어 있음"
            result.log(result.stop_reason, "ERROR")
            return result

        # 2. log 폴더
        log_folder = find_log_folder(batch_path,
                                     self.rules['log_folder_keywords'])
        if log_folder is None:
            result.status = "ERROR"
            result.stop_reason = "log 폴더가 없음"
            result.log(result.stop_reason, "ERROR")
            return result
        result.log(f"log 폴더 발견: {log_folder.name}")

        # 3. 체크파일
        check_file = find_check_file(log_folder,
                                     self.rules['check_file_keywords'])
        if check_file is None:
            result.status = "ERROR"
            result.stop_reason = "체크파일이 없음 (check 키워드 포함 txt 없음)"
            result.log(result.stop_reason, "ERROR")
            return result
        result.check_file = check_file.name
        result.log(f"체크파일 발견: {check_file.name}")

        # 4. 체크파일 파싱
        encoding = self.rules['check_file_format'].get('encoding', 'utf-8')
        try:
            data = parse_check_file(check_file, self.iccid_parser, encoding)
        except Exception as e:
            result.status = "ERROR"
            result.stop_reason = f"체크파일 읽기 실패: {e}"
            return result
        if not data:
            result.status = "ERROR"
            result.stop_reason = "체크파일에 유효한 ICCID 없음"
            return result
        result.total_rows = len(data)
        result.log(f"체크파일 분석: {len(data)}개 유효 ICCID")

        # 5~6. 일관성
        self._validate_consistency(data, result)
        # 7. 시작/마지막
        self._find_serial_range(data, result)
        # 8. 범위
        self._validate_serial_range(data, result)
        # 9. 미디어
        self._inspect_media(batch_path, result)

        has_violation = (
            result.consistency_violations or
            result.range_violations or
            result.media_violations
        )
        result.status = "FAIL" if has_violation else "PASS"
        result.log(f"===== 검수 완료: {result.status} =====")
        return result
