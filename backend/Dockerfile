# Use Python 3.11 slim image
FROM python:3.11.17-slim-trixie

# Install system dependencies including ffmpeg and unzip (for deno).
# Noto provides fallback glyphs for multilingual captions (including Hindi)
# and colour emoji. libass/fontconfig selects them when a chosen font lacks glyphs.
RUN apt-get update && apt-get install -y \
    ffmpeg \
    tesseract-ocr \
    tesseract-ocr-eng \
    curl \
    unzip \
    fonts-noto-core \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    fontconfig \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

# Install deno, pinned: yt-dlp uses it for YouTube JS challenges, and the dynamic-edits renderer (src/fx_runtime)
# runs fx-core on @napi-rs/canvas under it. The npm cache is baked below so renders work offline.
ARG DENO_VERSION=2.9.8
RUN curl -fsSL https://deno.land/install.sh | sh -s v${DENO_VERSION}
ENV DENO_DIR=/root/.deno
ENV PATH="/root/.deno/bin:${PATH}"

# TwitchDownloaderCLI (pinned): downloads the chat replay of a Twitch VOD so chat reactions can guide clip selection.
# Self-contained .NET build; invariant globalization avoids needing ICU in the slim image.
ARG TWITCH_DOWNLOADER_VERSION=1.56.5
ARG TARGETARCH
RUN case "${TARGETARCH:-amd64}" in arm64) asset=LinuxArm64 ;; *) asset=Linux-x64 ;; esac     && curl -fsSL -o /tmp/tdcli.zip "https://github.com/lay295/TwitchDownloader/releases/download/${TWITCH_DOWNLOADER_VERSION}/TwitchDownloaderCLI-${TWITCH_DOWNLOADER_VERSION}-${asset}.zip"     && unzip -o /tmp/tdcli.zip TwitchDownloaderCLI -d /usr/local/bin     && chmod +x /usr/local/bin/TwitchDownloaderCLI     && rm /tmp/tdcli.zip
ENV DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1

# Install uv package manager
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy pyproject.toml and uv.lock for dependency installation
COPY pyproject.toml uv.lock* ./

# New self-hosted setups can select CPU wheels without changing legacy builds.
ARG BACKEND_CPU_ONLY=false
# Frame scan's local models (open_clip, PANNs). Off by default: they add a few hundred MB and the weights are ~1 GB.
ARG FRAME_SCAN_LIBS=false
RUN uv venv .venv && \
    extra_libs="" && \
    if [ "$FRAME_SCAN_LIBS" = "true" ]; then extra_libs="--extra frame-scan"; fi && \
    if [ "$BACKEND_CPU_ONLY" = "true" ]; then \
      uv sync --frozen --extra cpu $extra_libs; \
    else \
      uv sync --frozen --extra cuda $extra_libs; \
    fi && \
    if [ "$FRAME_SCAN_LIBS" = "true" ] && [ "$BACKEND_CPU_ONLY" = "true" ]; then \
      uv pip install --python .venv/bin/python --reinstall-package torchvision --no-deps \
        --index-url https://download.pytorch.org/whl/cpu "torchvision==0.28.0"; \
    fi

# yt-dlp and its PO-token plugin are installed from uv.lock above.

# Bake the fx runtime's pinned npm/jsr cache into DENO_DIR before the source (layer cached on the lockfile).
# At runtime main.ts runs with --cached-only --frozen and never touches the network.
COPY src/fx_runtime/deno.json src/fx_runtime/deno.lock ./src/fx_runtime/
RUN cd src/fx_runtime && deno install --frozen

# Copy source code
COPY src/ ./src/
COPY LICENSE ./

# Copy fonts and transitions directories
COPY fonts/ ./fonts/
COPY transitions/ ./transitions/

# Self-hoster drop-in sounds and music beds for dynamic edits (FX_LIBRARY_DIR), like fonts/
COPY fx_library/ ./fx_library/

# Create necessary directories for video processing
RUN mkdir -p /app/uploads /app/clips /app/logs /tmp

# Expose the port FastAPI will run on
EXPOSE 8000

# Activate virtual environment and start the application
CMD [".venv/bin/uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
