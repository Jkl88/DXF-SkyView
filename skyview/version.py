APP_NAME = "DXF SkyView"
APP_VERSION = "0.4.4"
APP_AUTHOR = "Белоусов О. И."
APP_DESCRIPTION = (
    "Современный просмотрщик DXF и DWG с поддержкой привязок, "
    "измерений и инспекции свойств объектов."
)

GITHUB_REPO = "Jkl88/DXF-SkyView"
GITHUB_BRANCH = "main"
GITHUB_URL = f"https://github.com/{GITHUB_REPO}"
GITHUB_API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}"
RELEASE_EXE_NAME = "DXF-SkyView.exe"
# Запасной источник версии, если на GitHub ещё нет релизов (ветка main).
REMOTE_VERSION_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/skyview/version.py"
)
