@echo off
setlocal
cd /d "%~dp0"
echo Side-view posture: upright / leaning forward / leaning back.
echo In the preview, press L if your nose points LEFT, F if it points RIGHT.
echo C sets the current torso angle as neutral. R resets to image vertical.
echo Q or Esc exits. Sideways lean is not observable.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m posture webcam --viewpoint side --method side-angle --smoothing-window 3
) else if exist "..\..\work\venv\Scripts\python.exe" (
  "..\..\work\venv\Scripts\python.exe" -m posture webcam --viewpoint side --method side-angle --smoothing-window 3
) else (
  echo Python environment not found. Follow the setup steps in README.md.
)
pause
