"""MP4 파일 OCR 단독 테스트 스크립트.

사용법:
  py -3.14 scripts/test_video_ocr.py <MP4파일경로> [fps] [max_frames]

예시:
  py -3.14 scripts/test_video_ocr.py "C:/data/batch/video.mp4"
  py -3.14 scripts/test_video_ocr.py "C:/data/batch/video.mp4" 5 60
"""

import sys
import os
from pathlib import Path

# 프로젝트 src 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from usim_inspector.config import load_rules, ConfigError
from usim_inspector.iccid import IccidParser
from usim_inspector.media import extract_video_frames, ocr_image
from usim_inspector.tools import tools


def main():
    if len(sys.argv) < 2:
        print("사용법: py -3.14 scripts/test_video_ocr.py <MP4파일경로> [fps] [max_frames]")
        print("예시:   py -3.14 scripts/test_video_ocr.py video.mp4 5 60")
        sys.exit(1)

    # stdout UTF-8 설정
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    vid_path = Path(sys.argv[1]).resolve()
    fps = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    max_frames = int(sys.argv[3]) if len(sys.argv) > 3 else 120

    if not vid_path.exists():
        print(f"파일이 없습니다: {vid_path}")
        sys.exit(1)

    # 외부 도구 확인
    t = tools()
    print("===== 외부 도구 =====")
    for name, path in t.status().items():
        print(f"  {name:13}: {path}")
    print()

    if not t.ffmpeg:
        print("ffmpeg가 없어 프레임을 추출할 수 없습니다.")
        sys.exit(1)

    # rules.yaml 로드 (ICCID 파싱 규칙)
    rules_path = Path(__file__).resolve().parent.parent / 'rules' / 'rules.yaml'
    try:
        rules = load_rules(rules_path)
        parser = IccidParser.from_config(rules['iccid'])
        known_models = rules.get('known_models', {})
        print(f"rules.yaml 로드 완료: prefix={rules['iccid']['prefix']}, "
              f"알려진 모델 {len(known_models)}개\n")
    except ConfigError as e:
        print(f"rules.yaml 로드 실패: {e}")
        sys.exit(1)

    # 프레임 추출
    print(f"===== 프레임 추출 =====")
    print(f"  파일    : {vid_path.name}")
    print(f"  fps     : {fps}")
    print(f"  최대    : {max_frames}장")
    frames = extract_video_frames(vid_path, fps, max_frames)
    print(f"  결과    : {len(frames)}개 프레임 추출됨\n")

    if not frames:
        print("프레임 추출 실패. ffmpeg 설치 상태를 확인하세요.")
        sys.exit(1)

    # 프레임별 OCR
    print("===== 프레임별 OCR =====")
    confirmed_all: set = set()
    inferred_all: list = []
    tmp_dir = frames[0].parent

    for i, frame in enumerate(frames, 1):
        text = ocr_image(str(frame), is_video_frame=True)
        found = list(set(parser.extract_all(text)))
        new_found = [ic for ic in found if ic not in confirmed_all]
        confirmed_all.update(found)

        # 부분 인식 시도 (op_model 유추)
        new_inferred = []
        if confirmed_all or known_models:
            mdl_end = parser.mdl_slice.stop
            op_model = None
            for ic in confirmed_all:
                op_model = ic[:mdl_end]
                break
            if op_model is None:
                for model_code in known_models:
                    op_model = parser.prefix + model_code
                    break

            if op_model:
                raw = parser.infer_from_partial(text, op_model,
                                                confirmed=confirmed_all)
                for ic, serial in raw:
                    p = parser.parse(ic)
                    if known_models and (p is None or p.model not in known_models):
                        continue
                    new_inferred.append((ic, serial))
                    confirmed_all.add(ic)
                    inferred_all.append((ic, serial))

        if new_found or new_inferred:
            print(f"  [프레임 {i:03d}] 신규 발견:")
            for ic in new_found:
                print(f"    ✅ 확인: {ic}")
            for ic, serial in new_inferred:
                print(f"    ⚠️ 추정: {ic}  (시리얼 '{serial}' — 직접 확인 권고)")
        else:
            print(f"  [프레임 {i:03d}] 신규 없음 (누적 {len(confirmed_all)}개)")

    # 임시 폴더 정리
    import shutil
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass

    # 최종 요약
    inferred_dedup = list({ic: s for ic, s in inferred_all}.items())
    confirmed_list = sorted(confirmed_all - {ic for ic, _ in inferred_dedup})
    print()
    print("===== 최종 결과 =====")
    print(f"  확인된 ICCID : {len(confirmed_list)}개")
    for ic in confirmed_list:
        print(f"    ✅ {ic}")
    if inferred_dedup:
        print(f"  추정된 ICCID : {len(inferred_dedup)}개 (시리얼 직접 확인 필요)")
        for ic, serial in inferred_dedup:
            print(f"    ⚠️ {ic}  (시리얼 '{serial}')")
    if not confirmed_list and not inferred_dedup:
        print("  ICCID를 찾지 못했습니다.")
        print()
        print("  개선 방법:")
        print("    1. rules.yaml의 video_fps_sample 값을 높여보세요 (예: 10)")
        print("    2. ImageMagick이 설치되어 있는지 확인하세요 (전처리 품질 향상)")
        print("    3. 동영상 밝기/선명도가 낮은 경우 재촬영을 권장합니다")


if __name__ == '__main__':
    main()
