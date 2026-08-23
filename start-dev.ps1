# Save this as start-dev.ps1 in price-comparison-platform/
Write-Host "Starting Docker containers..."
docker start postgres-local
docker start redis-local

Write-Host "Starting backend..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd backend; .venv\Scripts\activate; uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

Write-Host "Starting frontend..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; npm run dev"

Write-Host "All services started!"
Write-Host "Backend: http://localhost:8000/docs"
Write-Host "Frontend: http://localhost:5173"