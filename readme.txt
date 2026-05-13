HOW TO RUN

start up venv
- 

db initialization and GTFS import 
- cd backend
- cd db
- python init_db.py

load today's GTFS into db 
- cd backend
- cd db
- python gtfs_processor.py

run backend server
- cd backend
uvicorn main:app --reload --host 127.0.0.1 --port 8080



frontend 

npm start



uvicorn server:app --port 8090 --reload
uvicorn main:app --reload --host 127.0.0.1 --port 8080
npm start