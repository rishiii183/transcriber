let currentJobId = null;
let currentResult = null;
let currentSegments = [];
let activeTab = 'url';
let selectedFile = null;
let eventSource = null;
let detectDebounceTimer = null;

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
  fetchHardwareInfo();
  setupUrlInputListener();
  setupDropzone();
  setupAudioPlayerSync();
  renderSessionHistory();
});

// Fetch hardware acceleration details & model cache status
async function fetchHardwareInfo() {
  const hwText = document.getElementById('hwText');
  try {
    const res = await fetch('/api/models');
    if (!res.ok) throw new Error('API offline');
    const data = await res.json();
    const hw = data.hardware;
    if (hw.is_gpu) {
      hwText.textContent = 'NVIDIA CUDA Acceleration';
    } else {
      hwText.textContent = 'CPU Multi-threaded Engine';
    }

    // Dynamically annotate models with offline cache status
    if (data.models && data.models.length > 0) {
      const select = document.getElementById('modelSelect');
      const currentVal = select.value || 'tiny';
      select.innerHTML = '';
      data.models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.id;
        const tag = m.is_cached ? '⚡ Ready Offline' : `⬇ Needs Download ${m.size}`;
        opt.textContent = `${m.name} (${m.speed} · ${tag})`;
        if (m.id === currentVal) opt.selected = true;
        select.appendChild(opt);
      });
    }
  } catch (err) {
    hwText.textContent = 'Local Engine (Offline)';
  }
}

// Tab Switching
function switchTab(tab) {
  activeTab = tab;
  const tabUrlBtn = document.getElementById('tabUrlBtn');
  const tabFileBtn = document.getElementById('tabFileBtn');
  const urlView = document.getElementById('urlInputView');
  const fileView = document.getElementById('fileInputView');

  if (tab === 'url') {
    tabUrlBtn.classList.add('active');
    tabFileBtn.classList.remove('active');
    urlView.classList.add('active');
    fileView.classList.remove('active');
  } else {
    tabFileBtn.classList.add('active');
    tabUrlBtn.classList.remove('active');
    fileView.classList.add('active');
    urlView.classList.remove('active');
  }
}

// URL input detection
function setupUrlInputListener() {
  const input = document.getElementById('urlInput');
  const clearBtn = document.getElementById('clearUrlBtn');

  input.addEventListener('input', () => {
    const val = input.value.trim();
    clearBtn.style.display = val ? 'inline-block' : 'none';

    clearTimeout(detectDebounceTimer);
    if (!val) {
      document.getElementById('platformPill').style.display = 'none';
      return;
    }

    detectDebounceTimer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/detect?url=${encodeURIComponent(val)}`);
        if (res.ok) {
          const info = await res.json();
          showPlatformPill(info);
        }
      } catch (e) {
        // Fallback local regex
      }
    }, 150);
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      startTranscription();
    }
  });
}

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    if (text) {
      const input = document.getElementById('urlInput');
      input.value = text.trim();
      input.dispatchEvent(new Event('input'));
      input.focus();
    }
  } catch (err) {
    alert('Please allow clipboard permissions or paste manually with Ctrl+V');
  }
}

function showPlatformPill(info) {
  const pill = document.getElementById('platformPill');
  const name = document.getElementById('platformName');
  if (!info || info.id === 'unknown') {
    pill.style.display = 'none';
    return;
  }
  name.textContent = info.name;
  pill.style.display = 'inline-flex';
}

function clearUrl() {
  const input = document.getElementById('urlInput');
  input.value = '';
  document.getElementById('clearUrlBtn').style.display = 'none';
  document.getElementById('platformPill').style.display = 'none';
  input.focus();
}

// File dropzone setup
function setupDropzone() {
  const dropzone = document.getElementById('dropzone');

  ['dragenter', 'dragover'].forEach(name => {
    dropzone.addEventListener(name, (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(name => {
    dropzone.addEventListener(name, (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
    });
  });

  dropzone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      setSelectedFile(files[0]);
    }
  });
}

function handleFileSelected(event) {
  const file = event.target.files[0];
  if (file) {
    setSelectedFile(file);
  }
}

function setSelectedFile(file) {
  selectedFile = file;
  const dropText = document.getElementById('dropzoneText');
  dropText.innerHTML = `Selected: <strong>${file.name}</strong> (${formatBytes(file.size)})`;
}

function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// Main Transcription Trigger
async function startTranscription() {
  const model = document.getElementById('modelSelect').value;
  const language = document.getElementById('langSelect').value;
  const vad_filter = document.getElementById('vadToggle').checked;

  let startEndpoint = '/api/transcribe';
  let requestOptions = {};

  if (activeTab === 'url') {
    const url = document.getElementById('urlInput').value.trim();
    if (!url) {
      alert('Please enter or paste a valid link (YouTube, X, Instagram, LinkedIn, etc.)');
      return;
    }
    requestOptions = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, model, language, vad_filter })
    };
  } else {
    if (!selectedFile) {
      alert('Please select or drop an audio/video file first.');
      return;
    }
    startEndpoint = '/api/upload';
    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('model', model);
    formData.append('language', language);
    formData.append('vad_filter', vad_filter);
    requestOptions = {
      method: 'POST',
      body: formData
    };
  }

  // Show processing UI
  showProcessing();

  try {
    const res = await fetch(startEndpoint, requestOptions);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to start transcription');
    }
    const data = await res.json();
    currentJobId = data.job_id;
    listenToProgress(currentJobId);
  } catch (err) {
    alert('Error: ' + err.message);
    resetToInput();
  }
}

// UI State Transitions
function showProcessing() {
  document.getElementById('inputCard').style.display = 'none';
  document.getElementById('resultCard').style.display = 'none';
  const procCard = document.getElementById('processingCard');
  procCard.style.display = 'flex';

  document.getElementById('progressStageTitle').textContent = 'Connecting...';
  document.getElementById('progressMessage').textContent = 'Preparing media extractor & local Whisper model...';
  document.getElementById('progressPercent').textContent = '0%';
  document.getElementById('progressBarFill').style.width = '0%';
  document.getElementById('liveStreamContent').textContent = 'Waiting for audio stream...';
  currentSegments = [];
}

function listenToProgress(jobId) {
  if (eventSource) {
    eventSource.close();
  }

  eventSource = new EventSource(`/api/stream/${jobId}`);
  const liveContent = document.getElementById('liveStreamContent');

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleProgressEvent(data);
    } catch (e) {
      console.error('Failed to parse SSE event', e);
    }
  };

  eventSource.onerror = (err) => {
    console.warn('SSE stream closed or interrupted', err);
    if (eventSource) eventSource.close();
  };
}

function handleProgressEvent(data) {
  const stageTitle = document.getElementById('progressStageTitle');
  const message = document.getElementById('progressMessage');
  const percentText = document.getElementById('progressPercent');
  const barFill = document.getElementById('progressBarFill');
  const liveContent = document.getElementById('liveStreamContent');

  if (data.type === 'download_progress') {
    stageTitle.textContent = 'Downloading Media Stream';
    message.textContent = data.message || `Downloading... ${data.percent}%`;
    const p = Math.max(5, Math.min(data.percent || 10, 50));
    percentText.textContent = `${Math.round(p)}%`;
    barFill.style.width = `${p}%`;
  } else if (data.type === 'media_ready') {
    stageTitle.textContent = 'Audio Stream Ready';
    message.textContent = `Extracted: ${data.title || 'Media audio'}`;
    percentText.textContent = '50%';
    barFill.style.width = '50%';
  } else if (data.type === 'status') {
    if (data.message && data.message.includes('Downloading')) {
      stageTitle.textContent = 'Downloading Offline Model (~460MB)';
    } else {
      stageTitle.textContent = 'Offline Speech Recognition';
    }
    message.textContent = data.message;
  } else if (data.type === 'segment') {
    const seg = data.segment;
    currentSegments.push(seg);

    // Update real-time recognition box
    liveContent.textContent += ` [${formatFriendlyTime(seg.start)}] ${seg.text}\n`;
    liveContent.scrollTop = liveContent.scrollHeight;

    const prog = data.progress_percent ? (50 + (data.progress_percent * 0.49)) : 75;
    percentText.textContent = `${Math.round(prog)}%`;
    barFill.style.width = `${prog}%`;
  } else if (data.type === 'complete' || data.type === 'finished') {
    percentText.textContent = '100%';
    barFill.style.width = '100%';
    if (eventSource) eventSource.close();

    const result = data.result || data;
    saveToSessionHistory(result);
    renderResults(result);
  } else if (data.type === 'error') {
    if (eventSource) eventSource.close();
    alert('Transcription Error: ' + data.message);
    resetToInput();
  }
}

// Render Results View
function renderResults(result) {
  currentResult = result;
  document.getElementById('processingCard').style.display = 'none';
  const resultCard = document.getElementById('resultCard');
  resultCard.style.display = 'flex';

  // Metadata
  const platform = result.platform || { name: 'Local Media' };
  const badge = document.getElementById('resPlatformBadge');
  badge.textContent = platform.name;

  document.getElementById('resTitle').textContent = result.title || 'Extracted Transcript';
  document.getElementById('resDuration').textContent = formatFriendlyTime(result.duration);
  document.getElementById('resLang').textContent = result.language ? result.language.toUpperCase() : 'AUTO';

  const speedup = result.speedup ? `${result.speedup}x` : 'Instant';
  document.getElementById('resSpeed').textContent = speedup;

  const segs = result.segments || currentSegments;
  document.getElementById('resSegCount').textContent = segs.length;

  const device = result.hardware ? (result.hardware.is_gpu ? 'CUDA' : 'CPU') : 'CPU';
  document.getElementById('resDevice').textContent = device;

  // Audio player
  const player = document.getElementById('audioPlayer');
  player.src = `/api/audio/${result.job_id || currentJobId}`;
  player.load();

  // Populate interactive transcript
  renderSegments(segs);
}

function renderSegments(segments, searchQuery = '') {
  const container = document.getElementById('transcriptContainer');
  container.innerHTML = '';

  if (!segments || segments.length === 0) {
    container.innerHTML = '<p style="color: var(--text-dim); text-align: center; padding: 20px;">No speech detected.</p>';
    return;
  }

  segments.forEach((seg, index) => {
    const item = document.createElement('div');
    item.className = 'segment-item';
    item.id = `seg-${index}`;
    item.dataset.start = seg.start;
    item.dataset.end = seg.end;

    let displayText = seg.text;
    if (searchQuery) {
      const regex = new RegExp(`(${escapeRegExp(searchQuery)})`, 'gi');
      displayText = displayText.replace(regex, '<span class="highlight">$1</span>');
    }

    item.innerHTML = `
      <span class="seg-timestamp" onclick="seekAudio(${seg.start}); event.stopPropagation();">${formatFriendlyTime(seg.start)}</span>
      <span class="seg-text">${displayText}</span>
    `;

    item.addEventListener('click', () => {
      seekAudio(seg.start);
    });

    container.appendChild(item);
  });
}

function escapeRegExp(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Audio Player Synchronization
function setupAudioPlayerSync() {
  const player = document.getElementById('audioPlayer');

  player.addEventListener('timeupdate', () => {
    const t = player.currentTime;
    const items = document.querySelectorAll('.segment-item');

    items.forEach(item => {
      const start = parseFloat(item.dataset.start);
      const end = parseFloat(item.dataset.end);
      if (t >= start && t <= end) {
        if (!item.classList.contains('active')) {
          item.classList.add('active');
          item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      } else {
        item.classList.remove('active');
      }
    });
  });
}

function seekAudio(seconds) {
  const player = document.getElementById('audioPlayer');
  player.currentTime = seconds;
  player.play();
}

// In-transcript search filter
function filterTranscript() {
  const query = document.getElementById('searchInput').value.trim();
  const segments = currentResult ? (currentResult.segments || currentSegments) : currentSegments;

  if (!query) {
    renderSegments(segments);
    return;
  }

  const filtered = segments.filter(s => s.text.toLowerCase().includes(query.toLowerCase()));
  renderSegments(filtered, query);
}

// Copy full text
async function copyFullText() {
  if (!currentResult && currentSegments.length === 0) return;
  const fullText = (currentResult && currentResult.full_text) 
    ? currentResult.full_text 
    : currentSegments.map(s => s.text).join(' ');

  try {
    await navigator.clipboard.writeText(fullText);
    const btnText = document.getElementById('copyBtnText');
    const old = btnText.textContent;
    btnText.textContent = '✓ Copied!';
    setTimeout(() => {
      btnText.textContent = old;
    }, 2000);
  } catch (err) {
    alert('Failed to copy to clipboard');
  }
}

// Export download
function exportFile(format) {
  if (!currentJobId) return;
  const url = `/api/export/${currentJobId}?format=${format}`;
  window.location.href = url;
}

// Reset to Input Card
function resetToInput() {
  if (eventSource) eventSource.close();
  document.getElementById('processingCard').style.display = 'none';
  document.getElementById('resultCard').style.display = 'none';
  document.getElementById('inputCard').style.display = 'block';

  const player = document.getElementById('audioPlayer');
  player.pause();
  player.src = '';
  renderSessionHistory();
}

// Session History Management
function saveToSessionHistory(result) {
  try {
    const raw = localStorage.getItem('transcribe_history') || '[]';
    const history = JSON.parse(raw);
    const item = {
      job_id: result.job_id || currentJobId,
      title: result.title || 'Media Transcript',
      platform: result.platform?.name || 'Media',
      duration: result.duration,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      result: result
    };
    // Prepend and limit to 10
    const updated = [item, ...history.filter(h => h.job_id !== item.job_id)].slice(0, 10);
    localStorage.setItem('transcribe_history', JSON.stringify(updated));
    renderSessionHistory();
  } catch (e) {
    console.warn('LocalStorage error', e);
  }
}

function renderSessionHistory() {
  try {
    const raw = localStorage.getItem('transcribe_history') || '[]';
    const history = JSON.parse(raw);
    const card = document.getElementById('historyCard');
    const list = document.getElementById('historyList');

    if (history.length === 0) {
      card.style.display = 'none';
      return;
    }

    card.style.display = 'block';
    list.innerHTML = '';

    history.forEach(item => {
      const row = document.createElement('div');
      row.className = 'history-item';
      row.innerHTML = `
        <div class="history-item-left">
          <span class="history-tag">${item.platform}</span>
          <span class="history-name">${item.title}</span>
        </div>
        <span class="history-time">${formatFriendlyTime(item.duration)} · ${item.timestamp}</span>
      `;
      row.addEventListener('click', () => {
        currentJobId = item.job_id;
        renderResults(item.result);
      });
      list.appendChild(row);
    });
  } catch (e) {
    console.warn('History render error', e);
  }
}

function clearSessionHistory() {
  localStorage.removeItem('transcribe_history');
  document.getElementById('historyCard').style.display = 'none';
}

// Time Formatting Helper
function formatFriendlyTime(seconds) {
  if (seconds === null || seconds === undefined || isNaN(seconds)) return '00:00';
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  if (hrs > 0) {
    return `${pad(hrs)}:${pad(mins)}:${pad(secs)}`;
  }
  return `${pad(mins)}:${pad(secs)}`;
}

function pad(num) {
  return num < 10 ? '0' + num : num;
}
