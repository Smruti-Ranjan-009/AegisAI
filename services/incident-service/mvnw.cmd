@REM Maven Wrapper startup script for Windows
@ECHO OFF
SETLOCAL

FOR %%i IN ("%~dp0.") DO SET "MAVEN_PROJECTBASEDIR=%%~fi"
SET "WRAPPER_JAR=%MAVEN_PROJECTBASEDIR%\.mvn\wrapper\maven-wrapper.jar"
SET "WRAPPER_URL=https://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper/3.3.2/maven-wrapper-3.3.2.jar"

IF EXIST "%WRAPPER_JAR%" GOTO run

ECHO Maven Wrapper JAR not found; downloading it from Maven Central...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop'; Invoke-WebRequest -UseBasicParsing -Uri '%WRAPPER_URL%' -OutFile '%WRAPPER_JAR%'"
IF ERRORLEVEL 1 EXIT /B 1

:run
IF DEFINED JAVA_HOME (
  SET "JAVA_EXE=%JAVA_HOME%\bin\java.exe"
) ELSE (
  SET "JAVA_EXE=java.exe"
)

"%JAVA_EXE%" "-Dmaven.multiModuleProjectDirectory=%MAVEN_PROJECTBASEDIR%" -classpath "%WRAPPER_JAR%" org.apache.maven.wrapper.MavenWrapperMain %*
EXIT /B %ERRORLEVEL%
