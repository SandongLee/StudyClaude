"""이미지/동영상에서 ICCID를 OCR로 검출.

Windows 한국어 환경 주의사항:
- subprocess 호출 시 text=True 금지 (cp949 자동 디코딩 → UTF-8 충돌)
- bytes로 받고 명시적으로 UTF-8 디코딩
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List
from .tools import tools


def ocr_image(image_path: str) -> str:
    """이미지에서 텍스트 추출. ImageMagick 전처리 → Tesseract OCR.

    실패 시 빈 문자열. 외부 도구 없으면 빈 문자열.
    """
    t = tools()
    if not t.tesseract:
        return ""

    tmp_path = None
    try:
        # ImageMagick으로 전처리 (있으면)
        if t.magick:
            tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            tmp.close()
            tmp_path = tmp.name
            subprocess.run(
                [t.magick, image_path,
                 '-resize', '300%',
                 '-colorspace', 'Gray',
                 '-contrast-stretch', '0.15x0.05%',
                 '-sharpen', '0x1',
                 tmp_path],
                check=False, capture_output=True, timeout=30
            )
            ocr_target = tmp_path
        else:
            ocr_target = image_path

        # 여러 PSM 모드로 OCR 시도 → 합치기
        out_parts = []
        for psm in ['6', '11', '3']:
            r = subprocess.run(
                [t.tesseract, ocr_target, '-', '--psm', psm,
                 '--oem', '3'],
                capture_output=True, timeout=30
            )
            # 핵심: bytes를 명시적 UTF-8로 디코딩 (cp949 자동디코딩 회피)
            stdout_text = r.stdout.decode('utf-8', errors='replace')
            out_parts.append(stdout_text)
        return "\n".join(out_parts)

    except Exception:
        return ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def extract_video_frames(video_path: Path, fps: float) -> List[Path]:
    """동영상에서 초당 fps장씩 프레임을 임시 폴더에 추출.

    Returns:
        추출된 프레임 파일 경로 리스트. 호출자가 작업 후 정리해야 함.

    Note:
        임시 폴더가 함수 종료 시 사라지지 않도록 호출자가 관리할 것.
        보통 tempfile.TemporaryDirectory 컨텍스트 안에서 호출.
    """
    t = tools()
    if not t.ffmpeg:
        return []

    out_dir = Path(tempfile.mkdtemp(prefix='usim_frames_'))
    frame_pattern = str(out_dir / 'f_%03d.jpg')
    try:
        subprocess.run(
            [t.ffmpeg, '-i', str(video_path), '-vf', f'fps={fps}',
             '-q:v', '2', frame_pattern, '-y'],
            capture_output=True, timeout=120, check=False
        )
    except Exception:
        return []

    return sorted(out_dir.glob('f_*.jpg'))
