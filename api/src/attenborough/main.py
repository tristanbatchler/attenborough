from fastapi import FastAPI
from starlette.responses import JSONResponse

app = FastAPI()


@app.get("/")
async def root():
    return JSONResponse(content=f'{"content": "Hello, world!"}')
