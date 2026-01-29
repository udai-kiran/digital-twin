#!/bin/bash
export PYTHONPATH="${APPDIR}/opt/audio_recorder:${PYTHONPATH}"
{{ python-executable }} -m audio_recorder "$@"
