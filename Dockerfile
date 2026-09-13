FROM python:3.12-slim
WORKDIR /app
# Only the page and the proxy; the other files are configs for Netlify/Vercel/PHP hosting
COPY index.html server.py ./
ENV HOST=0.0.0.0 PORT=8080 HISTORY_FILE=/data/history.json
# The evening's update history lives here; mount a volume on /data to keep it across restarts
RUN mkdir /data && chown nobody /data
EXPOSE 8080
USER nobody
CMD ["python3", "server.py"]
