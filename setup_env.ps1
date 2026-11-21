Write-Host "Creando entorno virtual ligero para el Agente Ollama..." -ForegroundColor Green
python -m venv .venv

Write-Host "Instalando dependencias (requests, customtkinter, duckduckgo-search, beautifulsoup4, PyPDF2, python-docx)..." -ForegroundColor Green
& .\.venv\Scripts\pip.exe install requests customtkinter duckduckgo-search beautifulsoup4 PyPDF2 python-docx

Write-Host "Instalacion completada." -ForegroundColor Green
