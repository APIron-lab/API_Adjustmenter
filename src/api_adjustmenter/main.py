from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .errors import AppError
from .models import NormalizeRequest, TransformRequest, DiffRequest, OkResponse, ErrResponse, DiffResponse
from .normalize import normalize_payload
from .transform import transform_payload
from .diff import diff_shapes

app = FastAPI(
    title="API Adjustmenter",
    version="0.1.0",
    description="Adjust messy JSON into a stable contract. Local MVP.",
)

@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "api-adjustmenter"}

@app.exception_handler(AppError)
def app_error_handler(request: Request, exc: AppError):
    payload = ErrResponse(error={"code": exc.code, "message": exc.message, "details": exc.details})
    return JSONResponse(status_code=exc.http_status, content=payload.model_dump())

@app.exception_handler(Exception)
def unhandled_error_handler(request: Request, exc: Exception):
    payload = ErrResponse(error={"code": "INTERNAL_ERROR", "message": "Unhandled server error", "details": {"type": exc.__class__.__name__}})
    return JSONResponse(status_code=500, content=payload.model_dump())

@app.post("/normalize", response_model=OkResponse)
def normalize(req: NormalizeRequest):
    output, meta = normalize_payload(req.input, req.options)
    return OkResponse(output=output, meta=meta)

@app.post("/transform", response_model=OkResponse)
def transform(req: TransformRequest):
    output, meta = transform_payload(req.input, req.rules)
    return OkResponse(output=output, meta=meta)

@app.post("/diff", response_model=DiffResponse)
def diff(req: DiffRequest):
    breaking, diff_result, meta = diff_shapes(req.before, req.after)
    return DiffResponse(breaking=breaking, diff=diff_result, meta=meta)
