"""Live audio → visualizer pipeline for the WLED panel.

A pluggable AudioSource yields PCM blocks; the SpectrumAnalyzer turns each into
log-spaced band levels; a Visualizer renders a 64x64 frame; the frame is pushed
to the panel through the display FrameSink seam. Capture is deliberately behind
a protocol so 'where the sound comes from' (Mac loopback, a mic, a network
feed) is a swap, not a rewrite.

Optional extra: ``uv sync --extra audio`` (numpy + sounddevice).
"""
