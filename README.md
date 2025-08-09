# Ollama RUN

 - ollama pull llama3
 - ollama serve

# Build analyzer

cd analyzer
dotnet build -c Release

# Start FastAPI

cd ../api
python -m venv .venv 
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Start Angular

cd ../ui
npm install
npm start  # http://localhost:4200

# Use the app

Zip your solution folder (must include .sln and all referenced projects/files).
Optionally add .md/.txt docs.
Click Analyze.
Read the generated Markdown.
