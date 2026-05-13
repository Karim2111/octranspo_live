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


- User selects a route, direction, and stop
- App queries the OC Transpo GTFS-Realtime api to find the active trip serving that route/direction
- App joins the active trip with the GTFS static data to find the scheduled arrival time at the selected stop
- These features are bundled and sent to a machine learning model
- The model returns a predicted arrival time based on patterns learned from historical realtime and schedule data
