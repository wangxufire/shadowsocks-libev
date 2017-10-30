@echo off

set root=%~dp0
set source=%root%src

goto start

:format
set filelist=%1
pushd %1
for /r "%filelist%" %%f in (*) do (
  if "%%~xf" == ".h" (
    echo 'format h file "%%f"'
    uncrustify -c %root%\.uncrustify.cfg -l C --replace --no-backup %%f
    DEL %%~dpf*.uncrustify >nul 2>nul
  ) else if "%%~xf" == ".c" (
    echo 'format c file "%%f"'
    uncrustify -c %root%\.uncrustify.cfg -l C --replace --no-backup %%f
    DEL %%~dpf*.uncrustify >nul 2>nul
  )
)
popd
goto end

:start
call :format %source%

:end
pause
