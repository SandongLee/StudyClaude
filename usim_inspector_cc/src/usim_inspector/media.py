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


def ocr_image(image_path: str, is_video_frame: bool = False) -> str:
    """이미지에서 텍스트 추출. ImageMagick 전처리 → Tesseract OCR.

    is_video_frame=True: MPEG 블록 노이즈 제거에 최적화된 전처리 적용.
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
            if is_video_frame:
                # 비디오 프레임: MPEG 블록 노이즈 → median, 강한 대비+선명화
                magick_cmd = [
                    t.magick, image_path,
                    '-resize', '400%',
                    '-colorspace', 'Gray',
                    '-median', '1',
                    '-contrast-stretch', '1x0.3%',
                    '-unsharp', '0x2+1.5+0.05',
                    tmp_path,
                ]
            else:
                magick_cmd = [
                    t.magick, image_path,
                    '-resize', '300%',
                    '-colorspace', 'Gray',
                    '-contrast-stretch', '0.15x0.05%',
                    '-sharpen', '0x1',
                    tmp_path,
                ]
            subprocess.run(magick_cmd, check=False, capture_output=True,
                           timeout=30)
            ocr_target = tmp_path
        else:
            ocr_target = image_path

        # 여러 PSM 모드로 OCR 시도 → 합치기
        psm_modes = ['6', '11', '3']
        if is_video_frame:
            psm_modes = ['6', '11', '3', '7']  # PSM 7: 한 줄 텍스트
        out_parts = []
        for psm in psm_modes:
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


def extract_video_frames(video_path: Path, fps: float,
                         max_frames: int = 0) -> List[Path]:
    """동영상에서 초당 fps장씩 프레임을 임시 폴더에 PNG로 추출.

    PNG 무손실 포맷을 사용하여 JPEG 압축 아티팩트를 방지.

    Args:
        max_frames: 0이면 무제한. 양수이면 추출 프레임 수 상한.

    Returns:
        추출된 프레임 파일 경로 리스트. 호출자가 작업 후 정리해야 함.
    """
    t = tools()
    if not t.ffmpeg:
        return []

    out_dir = Path(tempfile.mkdtemp(prefix='usim_frames_'))
    frame_pattern = str(out_dir / 'f_%05d.png')
    cmd = [t.ffmpeg, '-i', str(video_path), '-vf', f'fps={fps}']
    if max_frames > 0:
        cmd += ['-vframes', str(max_frames)]
    cmd += [frame_pattern, '-y']
    try:
        subprocess.run(cmd, capture_output=True, timeout=300, check=False)
    except Exception:
        return []

    return sorted(out_dir.glob('f_*.png'))
