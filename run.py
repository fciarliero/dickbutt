import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    print(f"Abrí http://localhost:{port}  —  para jugar online: ngrok http {port}")
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, log_level="warning")
