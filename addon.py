import logging
import asyncio
import urllib.parse
import markupsafe
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends, Response
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from config import Config
from tg_client import tg_client_manager
from utils import (
    format_size,
    matches_episode,
    get_metadata_from_cinemeta,
    matches_subtitle,
    get_search_query_from_filename
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] (%(name)s) - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("stremio_addon")

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        print("\n" + "=" * 60)
        print("   TELEGRAM ADDON BY SUNILROY-DEV")
        print("   GitHub: https://github.com/SunilRoy-dev/stremio-telegram-debrid")
        print("   For educational and personal testing only.")
        print("=" * 60 + "\n")
        
        Config.validate()
        await tg_client_manager.start()
        yield
    finally:
        await tg_client_manager.stop()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def verify_api_key(request: Request):
    if Config.API_KEY:
        api_key = request.query_params.get("api_key", "")
        if api_key != Config.API_KEY:
            raise HTTPException(status_code=403, detail="Unauthorized: Invalid API Key")

def get_manifest(api_key: str = ""):
    query_suffix = f"?api_key={api_key}" if api_key else ""
    return {
        "id": "community.telegram.stremio.addon",
        "version": "1.0.0",
        "name": "Telegram Addon by SunilRoy-dev",
        "description": "Personal Telegram streaming proxy. For educational & personal testing only. Do not use for unauthorized hosting of copyrighted media.",
        "logo": "https://upload.wikimedia.org/wikipedia/commons/8/82/Telegram_logo.svg",
        "resources": ["catalog", "stream", "subtitles"],
        "types": ["movie", "series"],
        "idPrefixes": ["tgfile_", "tt"],
        "catalogs": [
            {
                "type": "movie",
                "id": "tg_catalog_movies",
                "name": "Telegram Videos",
                "extra": [{"name": "search", "isRequired": False}]
            },
            {
                "type": "series",
                "id": "tg_catalog_series",
                "name": "Telegram Segmented Videos",
                "extra": [{"name": "search", "isRequired": False}]
            }
        ],
        "behaviorHints": {
            "configurable": False,
            "configurationRequired": False
        }
    }

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def landing(request: Request):
    api_key = request.query_params.get("api_key", "")
    manifest_url = f"{Config.ADDON_URL}/manifest.json"
    if api_key:
        manifest_url += f"?api_key={urllib.parse.quote(api_key)}"
        
    escaped_manifest_url = markupsafe.escape(manifest_url)
    escaped_stremio_url = markupsafe.escape(manifest_url.replace('http://', '').replace('https://', ''))
    
    html_content = f"""
    <html>
        <head>
            <title>Telegram Addon by SunilRoy-dev</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: #0e1621;
                    color: #ffffff;
                    text-align: center;
                    padding: 50px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background-color: #17212b;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.5);
                }}
                h1 {{ color: #2481cc; }}
                a.btn {{
                    display: inline-block;
                    background-color: #2481cc;
                    color: white;
                    padding: 12px 25px;
                    text-decoration: none;
                    font-weight: bold;
                    border-radius: 5px;
                    margin-top: 20px;
                }}
                a.btn:hover {{ background-color: #2895e7; }}
                input.url-box {{
                    width: 100%;
                    padding: 10px;
                    background-color: #24303f;
                    border: 1px solid #2481cc;
                    color: white;
                    border-radius: 5px;
                    text-align: center;
                    font-size: 14px;
                    margin-top: 15px;
                }}
                .footer {{
                    margin-top: 40px;
                    font-size: 13px;
                    color: #7f91a4;
                    line-height: 1.6;
                }}
                .footer a {{
                    color: #2481cc;
                    text-decoration: none;
                    font-weight: bold;
                }}
                .footer a:hover {{
                    text-decoration: underline;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <img src="https://upload.wikimedia.org/wikipedia/commons/8/82/Telegram_logo.svg" width="80" alt="Logo">
                <h1>Telegram Addon</h1>
                <p>Stream your private Telegram channel files directly inside Stremio.</p>
                
                <p>Use the link below to configure/install this addon:</p>
                <input class="url-box" type="text" readonly value="{escaped_manifest_url}">
                
                <a class="btn" href="stremio://{escaped_stremio_url}">Install on Stremio</a>
                
                <div class="footer">
                    Developed by <a href="https://github.com/SunilRoy-dev" target="_blank">SunilRoy-dev</a> | Licensed under MIT<br>
                    <em>For educational and personal testing only. Do not use for illegal purposes or copyrighted distribution.</em>
                </div>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.api_route("/manifest.json", methods=["GET", "HEAD"])
async def manifest_endpoint(api_key: str = ""):
    if Config.API_KEY and api_key != Config.API_KEY:
        return JSONResponse({"detail": "Unauthorized: Invalid API Key"}, status_code=403)
    return get_manifest(api_key)

@app.get("/catalog/{type}/{catalog_id}.json", dependencies=[Depends(verify_api_key)])
@app.get("/catalog/{type}/{catalog_id}/{extra}.json", dependencies=[Depends(verify_api_key)])
async def catalog_handler(
    type: str, 
    catalog_id: str, 
    extra: str = None,
    api_key: str = ""
):
    if type not in ["movie", "series"]:
        return {"metas": []}
        
    query = ""
    if extra:
        params = urllib.parse.parse_qs(extra)
        if "search" in params:
            query = params["search"][0]

    try:
        messages = await tg_client_manager.search_messages(query=query, limit=50)
    except Exception as e:
        logger.error(f"Catalog search failed: {e}")
        return {"metas": []}

    metas = []
    for msg in messages:
        media = msg.video or msg.document or msg.audio
        if not media:
            continue
            
        file_name = getattr(media, "file_name", None) or msg.caption or f"Telegram File {msg.id}"
        file_size = media.file_size
        caption = msg.caption or ""
        
        tg_id = f"tgfile_{msg.chat.id}_{msg.id}"
        
        metas.append({
            "id": tg_id,
            "type": type,
            "name": file_name,
            "description": f"💾 Telegram File\n📦 Size: {format_size(file_size)}\n💬 {caption}" if caption else f"💾 Telegram File\n📦 Size: {format_size(file_size)}",
            "poster": None,
        })
        
    return {"metas": metas}

async def find_subtitles_for_video(video_filename: str, api_key: str = "", cached_messages=None) -> list:
    subtitles = []
    search_results = cached_messages or []
    query_param = f"?api_key={api_key}" if api_key else ""
    
    if not search_results:
        query = get_search_query_from_filename(video_filename)
        if query:
            try:
                search_results = await tg_client_manager.search_messages(query=query, limit=20)
            except Exception as e:
                logger.error(f"Subtitle search failed for '{query}': {e}")
                
    seen_msg_ids = set()
    for msg in search_results:
        if msg.id in seen_msg_ids:
            continue
            
        doc = msg.document or msg.audio or msg.video
        if not doc:
            continue
            
        sub_fn = getattr(doc, "file_name", "") or ""
        if sub_fn.lower().endswith(('.srt', '.vtt', '.ass')):
            if matches_subtitle(video_filename, sub_fn):
                seen_msg_ids.add(msg.id)
                
                lang = "eng"
                sub_fn_lower = sub_fn.lower()
                if ".spa" in sub_fn_lower or "spanish" in sub_fn_lower:
                    lang = "spa"
                elif ".fre" in sub_fn_lower or "french" in sub_fn_lower:
                    lang = "fre"
                
                subtitles.append({
                    "id": f"tgsub_{msg.chat.id}_{msg.id}",
                    "url": f"{Config.ADDON_URL}/stream/subtitle/{msg.chat.id}/{msg.id}/{urllib.parse.quote(sub_fn)}{query_param}",
                    "lang": lang
                })
                
    return subtitles

@app.get("/stream/{type}/{stream_id}.json")
async def stream_handler(
    type: str, 
    stream_id: str,
    api_key: str = ""
):
    if Config.API_KEY and api_key != Config.API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    streams = []
    query_param = f"?api_key={api_key}" if api_key else ""

    if stream_id.startswith("tgfile_"):
        parts = stream_id.split("_")
        if len(parts) >= 3:
            chat_id = parts[1]
            msg_id = parts[2]
            try:
                try:
                    chat_id_val = int(chat_id)
                except ValueError:
                    chat_id_val = chat_id
                msg = await tg_client_manager.get_message(int(msg_id), chat_id=chat_id_val)
                media = msg.video or msg.document or msg.audio
                file_name = getattr(media, "file_name", "video.mp4") or "video.mp4"
                file_size = media.file_size
                
                stream_url = f"{Config.ADDON_URL}/stream/file/{chat_id}/{msg_id}/{urllib.parse.quote(file_name)}{query_param}"
                subtitles = await find_subtitles_for_video(file_name, api_key=api_key)
                
                streams.append({
                    "name": "▶ TG Play",
                    "title": f"{file_name}\n💾 Direct stream | 📦 {format_size(file_size)}",
                    "url": stream_url,
                    "subtitles": subtitles,
                    "behaviorHints": {
                        "notWebReady": True,
                    }
                })
            except Exception as e:
                logger.error(f"Failed resolving direct stream for {stream_id}: {e}")

    elif stream_id.startswith("tt"):
        imdb_id = stream_id
        season = None
        episode = None
        
        if ":" in stream_id:
            parts = stream_id.split(":")
            imdb_id = parts[0]
            season = int(parts[1])
            episode = int(parts[2])
            
        try:
            meta = await get_metadata_from_cinemeta(type, imdb_id)
            movie_name = meta.get("name")
            
            if movie_name:
                logger.info(f"Resolved IMDb {imdb_id} to '{movie_name}'. Searching Telegram...")
                tg_results = await tg_client_manager.search_messages(query=movie_name, limit=50)
                
                for msg in tg_results:
                    media = msg.video or msg.document or msg.audio
                    file_name = getattr(media, "file_name", None) or msg.caption or ""
                    
                    if type == "series" and not matches_episode(file_name, season, episode):
                        continue
                        
                    file_size = media.file_size
                    stream_url = f"{Config.ADDON_URL}/stream/file/{msg.chat.id}/{msg.id}/{urllib.parse.quote(file_name)}{query_param}"
                    subtitles = await find_subtitles_for_video(file_name, api_key=api_key, cached_messages=tg_results)
                    
                    streams.append({
                        "name": "▶ TG Channel",
                        "title": f"{file_name}\n💾 Telegram File | 📦 {format_size(file_size)}",
                        "url": stream_url,
                        "subtitles": subtitles,
                        "behaviorHints": {
                            "notWebReady": True,
                        }
                    })
        except Exception as e:
            logger.error(f"Cinemeta search/resolve failed: {e}")

    return {"streams": streams}

@app.get("/subtitles/{type}/{id}.json")
@app.get("/subtitles/{type}/{id}/{extra}.json")
async def subtitles_handler(
    type: str,
    id: str,
    extra: str = None,
    api_key: str = ""
):
    if Config.API_KEY and api_key != Config.API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    subtitles = []
    
    if id.startswith("tgfile_"):
        parts = id.split("_")
        if len(parts) >= 3:
            chat_id = parts[1]
            msg_id = parts[2]
            try:
                try:
                    chat_id_val = int(chat_id)
                except ValueError:
                    chat_id_val = chat_id
                msg = await tg_client_manager.get_message(int(msg_id), chat_id=chat_id_val)
                media = msg.video or msg.document or msg.audio
                video_filename = getattr(media, "file_name", "") or ""
                if video_filename:
                    subtitles = await find_subtitles_for_video(video_filename, api_key=api_key)
            except Exception as e:
                logger.error(f"Failed to resolve subtitles for direct catalog ID {id}: {e}")
                
    elif id.startswith("tt"):
        imdb_id = id
        season = None
        episode = None
        if ":" in id:
            parts = id.split(":")
            imdb_id = parts[0]
            season = int(parts[1])
            episode = int(parts[2])
            
        try:
            video_filename = None
            if extra:
                decoded_extra = urllib.parse.unquote(extra)
                if "?" in decoded_extra:
                    decoded_extra = decoded_extra.split("?", 1)[0]
                params = urllib.parse.parse_qs(decoded_extra)
                if "filename" in params:
                    video_filename = params["filename"][0]

            if video_filename:
                logger.info(f"Resolving subtitles directly for filename: '{video_filename}'")
                subtitles = await find_subtitles_for_video(video_filename, api_key=api_key)
            else:
                meta = await get_metadata_from_cinemeta(type, imdb_id)
                movie_name = meta.get("name")
                if movie_name:
                    tg_results = await tg_client_manager.search_messages(query=movie_name, limit=50)
                    for msg in tg_results:
                        media = msg.video or msg.document or msg.audio
                        fn = getattr(media, "file_name", "") or msg.caption or ""
                        if type == "series" and not matches_episode(fn, season, episode):
                            continue
                        video_filename = fn
                        break
                    
                    if video_filename:
                        subtitles = await find_subtitles_for_video(video_filename, api_key=api_key, cached_messages=tg_results)
        except Exception as e:
            logger.error(f"Failed to resolve subtitles for IMDb ID {id}: {e}")
            
    return {"subtitles": subtitles}

@app.api_route("/stream/subtitle/{chat_id}/{message_id}/{filename}", methods=["GET", "HEAD"])
async def tg_subtitle_proxy(
    chat_id: str, 
    message_id: int, 
    filename: str,
    request: Request,
    api_key: str = ""
):
    if Config.API_KEY and api_key != Config.API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    try:
        try:
            chat_id_val = int(chat_id)
        except ValueError:
            chat_id_val = chat_id
        msg = await tg_client_manager.get_message(message_id, chat_id=chat_id_val)
    except Exception as e:
        logger.error(f"Proxy failed to fetch subtitle message: {e}")
        raise HTTPException(status_code=404, detail="Subtitle file not found")
        
    if not msg:
        raise HTTPException(status_code=404, detail="Subtitle message not found")
        
    media = msg.document or msg.audio or msg.video
    if not media:
        raise HTTPException(status_code=404, detail="No media found in subtitle message")
        
    content_type = "text/plain"
    filename_lower = filename.lower()
    if filename_lower.endswith(".srt"):
        content_type = "application/x-subrip"
    elif filename_lower.endswith(".vtt"):
        content_type = "text/vtt"
    elif filename_lower.endswith(".ass"):
        content_type = "text/plain"
        
    headers = {
        "Content-Disposition": f'inline; filename="{filename}"',
        "Access-Control-Allow-Origin": "*",
        "Content-Length": str(media.file_size),
    }
    
    if request.method == "HEAD":
        return Response(
            status_code=200,
            media_type=content_type,
            headers=headers
        )
        
    try:
        logger.info(f"Downloading subtitle file from Telegram: {filename} (msg ID {message_id})")
        file_buffer = await tg_client_manager.client.download_media(msg, in_memory=True)
        content = file_buffer.getvalue()
    except Exception as e:
        logger.error(f"Failed to download subtitle file: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve subtitle media")
        
    return Response(
        content=content,
        media_type=content_type,
        headers=headers
    )

@app.api_route("/stream/file/{chat_id}/{message_id}/{filename}", methods=["GET", "HEAD"])
async def tg_stream_proxy(
    chat_id: str, 
    message_id: int, 
    filename: str, 
    request: Request,
    api_key: str = ""
):
    if Config.API_KEY and api_key != Config.API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    try:
        try:
            chat_id_val = int(chat_id)
        except ValueError:
            chat_id_val = chat_id
        msg = await tg_client_manager.get_message(message_id, chat_id=chat_id_val)
    except Exception as e:
        logger.error(f"Proxy failed to fetch message: {e}")
        raise HTTPException(status_code=404, detail="Media file not found")
        
    if not msg:
        raise HTTPException(status_code=404, detail="Media message not found")
        
    media = msg.video or msg.document or msg.audio
    if not media:
        raise HTTPException(status_code=404, detail="No playable media found in message")
        
    file_size = media.file_size
    mime_type = media.mime_type or "video/mp4"
    
    if request.method == "GET":
        asyncio.create_task(
            tg_client_manager.send_play_log(filename, chat_id_val, message_id)
        )
    
    range_header = request.headers.get("Range")
    start = 0
    end = file_size - 1
    
    if range_header:
        try:
            bytes_range = range_header.replace("bytes=", "").split("-")
            if bytes_range[0]:
                start = int(bytes_range[0])
            if len(bytes_range) > 1 and bytes_range[1]:
                end = int(bytes_range[1])
        except ValueError:
            pass
            
    content_length = end - start + 1
    
    chunk_size = 1024 * 1024
    offset = start // chunk_size
    skip_bytes = start % chunk_size
    
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Disposition": f'inline; filename="{filename}"',
    }
    
    status_code = 206 if range_header else 200
    
    if request.method == "HEAD":
        logger.info(f"HEAD request for media '{filename}' (bytes {start}-{end}/{file_size}) - Status {status_code}")
        return Response(
            status_code=status_code,
            media_type=mime_type,
            headers=headers
        )
        
    async def file_generator():
        bytes_sent = 0
        first_chunk = True
        try:
            async for chunk in tg_client_manager.client.stream_media(media, offset=offset):
                if first_chunk:
                    first_chunk = False
                    if skip_bytes < len(chunk):
                        chunk = chunk[skip_bytes:]
                    else:
                        continue
                        
                if bytes_sent + len(chunk) > content_length:
                    chunk = chunk[:content_length - bytes_sent]
                    
                yield chunk
                bytes_sent += len(chunk)
                
                if bytes_sent >= content_length:
                    break
        except Exception as e:
            logger.error(f"Streaming error on message {message_id}: {e}")
            
    logger.info(f"Streaming media '{filename}' (bytes {start}-{end}/{file_size}) - Status {status_code}")
    
    return StreamingResponse(
        file_generator(),
        status_code=status_code,
        media_type=mime_type,
        headers=headers
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("addon:app", host="0.0.0.0", port=Config.PORT, reload=True)
