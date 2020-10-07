::    RESTful Interface Tool Sample Script for HPE iLO Products    ::
::  Copyright 2014, 2020 Hewlett Packard Enterprise Development LP ::

:: Description:  This is a sample batch script to return the       ::
::               version of firmware currently running .           ::

:: NOTE:  You will need to replace the USER_LOGIN and PASSWORD     ::
::        values with values that are appropriate for your         ::
::        environment.                                             ::

::        Firmware support information for this script:            ::
::            iLO 5 - All versions                                 ::
::            iLO 4 - All versions.                                ::

@echo off
set argC=0
for %%x in (%*) do Set /A argC+=1
if %argC% EQU 3 goto :remote
if %argC% EQU 0 goto :local
goto :error

:local
ilorest select Manager. -u USER_LOGIN -p PASSWORD
::The line below is for iLO 5                                      ::
ilorest list Oem/Hpe/Firmware/Current/VersionString
:: Uncomment the following line for iLO 4                          ::
::ilorest list Oem/Hp/Firmware/Current/VersionString
ilorest logout
goto :exit
:remote
ilorest select Manager. --url=%1 -u %2 -p %3
::The line below is for iLO 5                                      ::
ilorest list Oem/Hpe/Firmware/Current/VersionString
:: Uncomment the following line for iLO 4                          ::
::ilorest list Oem/Hp/Firmware/Current/VersionString
ilorest logout
goto :exit

:error
echo Usage:
echo        remote: Get_FW_Version.bat ^<iLO url^> ^<iLO username^>  ^<iLO password^>
echo        local:  Get_FW_Version.bat

:exit