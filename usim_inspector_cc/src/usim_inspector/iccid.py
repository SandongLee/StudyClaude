"""ICCID 문자열 파싱과 필드 분해.

검수 규칙(prefix, 자릿수, 필드 위치)은 모두 외부 설정(rules.yaml)에서 주입받는다.
하드코딩 금지.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class IccidFields:
    """ICCID에서 추출된 필드 모음."""
    iccid: str
    operator: str
    model: str
    serial: str
    row: Optional[int] = None  # 체크파일 행번호 (있을 때)


class IccidParser:
    """rules.yaml의 iccid 섹션에 기반하여 ICCID를 파싱."""

    def __init__(self, prefix: str, total_length: int,
                 operator_range: tuple, model_range: tuple,
                 serial_range: tuple) -> None:
        """
        Args:
            prefix: ICCID 시작 문자열 (예: "898205")
            total_length: 전체 자릿수 (예: 20)
            operator_range: (start, end) 1-based, 끝 포함
            model_range: (start, end)
            serial_range: (start, end)
        """
        self.prefix = prefix
        self.length = total_length
        # 1-based, 끝 포함 → Python slice (0-based, 끝 미포함)
        self.op_slice = slice(operator_range[0] - 1, operator_range[1])
        self.mdl_slice = slice(model_range[0] - 1, model_range[1])
        self.ser_slice = slice(serial_range[0] - 1, serial_range[1])

        # 정규식: prefix + 충분히 긴 자릿수
        digits_after = total_length - len(prefix) - 1
        self.regex = re.compile(
            rf'{prefix}[0-9]{{{digits_after}}}[A-Fa-f0-9]',
            re.IGNORECASE
        )

    @classmethod
    def from_config(cls, cfg: dict) -> 'IccidParser':
        """rules.yaml의 iccid 섹션 dict로부터 생성."""
        f = cfg['fields']
        return cls(
            prefix=cfg['prefix'],
            total_length=cfg['total_length'],
            operator_range=(f['operator']['start'], f['operator']['end']),
            model_range=(f['model']['start'], f['model']['end']),
            serial_range=(f['serial']['start'], f['serial']['end']),
        )

    def parse(self, iccid: str) -> Optional[IccidFields]:
        """ICCID 문자열을 분해. 형식 안 맞으면 None."""
        iccid = iccid.strip().upper()
        if len(iccid) != self.length or not iccid.startswith(self.prefix):
            return None
        return IccidFields(
            iccid=iccid,
            operator=iccid[self.op_slice],
            model=iccid[self.mdl_slice],
            serial=iccid[self.ser_slice],
        )

    def extract_all(self, text: str) -> List[str]:
        """텍스트에서 완전히 인식된 ICCID 목록 반환."""
        return [m.upper() for m in self.regex.findall(text)]

    def infer_from_partial(
        self, text: str, op_model: str,
        confirmed: Optional[set] = None
    ) -> List[Tuple[str, str]]:
        """사업자+모델코드가 알려진 경우, OCR에서 앞부분이 잘린 ICCID를 복원.

        같은 배치의 모든 ICCID는 사업자+모델코드가 동일하다는 사실을 이용해
        시리얼 번호가 포함된 ICCID 후반부를 찾아 전체를 재구성한다.
        시리얼(serial_range)은 반드시 OCR에서 직접 읽힌 범위 내에 있어야 한다.

        Args:
            text: OCR 결과 텍스트
            op_model: 확인된 사업자+모델코드 (예: '89820522046', 최대 11자)
            confirmed: 이미 완전 인식된 ICCID 집합 (중복 제외용)

        Returns:
            (재구성_ICCID, OCR에서_직접_읽은_시리얼) 튜플 리스트
        """
        already = confirmed if confirmed is not None else set(self.extract_all(text))
        results: List[Tuple[str, str]] = []
        ser_start = self.ser_slice.start  # 0-based (예: 11)

        # missing: OCR이 잘라낸 앞부분 자릿수 (1 ~ 시리얼 시작 전까지)
        for missing in range(1, min(ser_start, len(op_model)) + 1):
            head = op_model[:missing]
            tail_len = self.length - missing

            tail_pat = re.compile(
                rf'(?<![0-9A-Fa-f])[0-9]{{{tail_len - 1}}}[A-Fa-f0-9]'
                rf'(?![0-9A-Fa-f])',
                re.IGNORECASE
            )
            for m in tail_pat.finditer(text):
                candidate = (head + m.group()).upper()
                if len(candidate) != self.length:
                    continue
                if not self.regex.fullmatch(candidate):
                    continue
                if candidate in already:
                    continue
                # tail 내에서 시리얼 위치 추출
                serial_read = m.group()[ser_start - missing:
                                        self.ser_slice.stop - missing]
                results.append((candidate, serial_read))
                already.add(candidate)

        return results
