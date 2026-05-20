"""외부 도구(ImageMagick, Tesseract, FFmpeg) 탐색.

Windows 한국어 환경에서 PATH뿐 아니라 Program Files 폴더도 자동 탐색한다.
"""

import os
import platform
import shutil
from typing import Optional

IS_WINDOWS = platform.system() == 'Windows'


def find_tool(*candidates: str) -> Optional[str]:
    """주어진 이름 후보들 중 PATH에서 찾을 수 있는 첫 번째 도구의 경로 반환.

    Windows의 경우 일반적인 설치 경로도 함께 탐색한다.
    """
    # 1) PATH에서 탐색
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path

    # 2) Windows 기본 설치 경로 탐색
    if IS_WINDOWS:
        common_dirs = [
            r"C:\Program Files\Tesseract-OCR",
            r"C:\Program Files (x86)\Tesseract-OCR",
            r"C:\ffmpeg\bin",
            r"C:\Program Files\ffmpeg\bin",
        ]
        # ImageMagick은 버전에 따라 폴더명이 다양함 → 와일드카드 탐색
        for pf in [r"C:\Program Files", r"C:\Program Files (x86)"]:
            if os.path.isdir(pf):
                for sub in os.listdir(pf):
                    name_l = sub.lower()
                    if ('imagemagick' in name_l or 'tesseract' in name_l
                            or 'ffmpeg' in name_l):
                        common_dirs.append(os.path.join(pf, sub))
                        common_dirs.append(os.path.join(pf, sub, 'bin'))

        # winget 설치 경로 탐색 (%LOCALAPPDATA%\Microsoft\WinGet\Packages\...)
        winget_base = os.path.join(os.environ.get('LOCALAPPDATA', ''),
                                   'Microsoft', 'WinGet', 'Packages')
        if os.path.isdir(winget_base):
            for pkg in os.listdir(winget_base):
                if any(k in pkg.lower() for k in ('ffmpeg', 'imagemagick', 'tesseract')):
                    pkg_path = os.path.join(winget_base, pkg)
                    for root, dirs, _ in os.walk(pkg_path):
                        if os.path.basename(root).lower() == 'bin':
                            common_dirs.append(root)

        for d in common_dirs:
            for name in candidates:
                p = os.path.join(d, name + '.exe')
                if os.path.isfile(p):
                    return p
    return None


class ExternalTools:
    """외부 도구 경로를 한 번만 탐색하고 캐싱하는 싱글톤."""

    def __init__(self) -> None:
        # ImageMagick: Linux/macOS='convert', Windows 7.x='magick'
        if IS_WINDOWS:
            self.magick = find_tool('magick', 'convert')
        else:
            self.magick = find_tool('convert', 'magick')
        self.tesseract = find_tool('tesseract')
        self.ffmpeg = find_tool('ffmpeg')

    def status(self) -> dict:
        """진단용 상태 dict."""
        return {
            'imagemagick': self.magick or '❌ 없음',
            'tesseract': self.tesseract or '❌ 없음',
            'ffmpeg': self.ffmpeg or '❌ 없음',
        }

    def all_ready(self) -> bool:
        return all([self.magick, self.tesseract, self.ffmpeg])

    def missing(self) -> list:
        """없는 도구 이름들."""
        m = []
        if not self.tesseract:
            m.append("Tesseract OCR")
        if not self.ffmpeg:
            m.append("FFmpeg")
        if not self.magick:
            m.append("ImageMagick")
        return m


_INSTANCE: Optional[ExternalTools] = None


def tools() -> ExternalTools:
    """캐싱된 ExternalTools 인스턴스 반환."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ExternalTools()
    return _INSTANCE
