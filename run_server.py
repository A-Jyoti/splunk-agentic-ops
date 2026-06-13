import uvicorn

if __name__ == "__main__":
    print("Starting Real-Time Event Ticketing Engine (Live Server)")
    # This ensures it runs without auto-shutting down and without test data
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
