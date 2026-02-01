import React, { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

// Fix for default marker icons in react-leaflet
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: require('leaflet/dist/images/marker-icon-2x.png'),
  iconUrl: require('leaflet/dist/images/marker-icon.png'),
  shadowUrl: require('leaflet/dist/images/marker-shadow.png'),
});

const API_BASE_URL = 'http://localhost:8080/api';

function App() {
  const [stops, setStops] = useState([]);
  const [selectedStop, setSelectedStop] = useState(null);
  const [arrivals, setArrivals] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [userLocation, setUserLocation] = useState(null);
  const [mapCenter, setMapCenter] = useState([45.4215, -75.6972]); // Ottawa center

  // Get user's location
  useEffect(() => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const location = {
            lat: position.coords.latitude,
            lon: position.coords.longitude
          };
          setUserLocation(location);
          setMapCenter([location.lat, location.lon]);
          fetchNearbyStops(location.lat, location.lon);
        },
        (error) => {
          console.error('Error getting location:', error);
          fetchAllStops();
        }
      );
    } else {
      fetchAllStops();
    }
  }, []);

  const fetchNearbyStops = async (lat, lon, radius = 1000) => {
    setLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/stops?lat=${lat}&lon=${lon}&radius=${radius}`
      );
      const data = await response.json();
      setStops(data);
    } catch (error) {
      console.error('Error fetching stops:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchAllStops = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/stops`);
      const data = await response.json();
      setStops(data);
    } catch (error) {
      console.error('Error fetching stops:', error);
    } finally {
      setLoading(false);
    }
  };

  const searchStops = async () => {
    if (!searchQuery.trim()) {
      if (userLocation) {
        fetchNearbyStops(userLocation.lat, userLocation.lon);
      } else {
        fetchAllStops();
      }
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/stops?search=${encodeURIComponent(searchQuery)}`
      );
      const data = await response.json();
      setStops(data);
      
      // Center map on first result
      if (data.length > 0) {
        setMapCenter([data[0].lat, data[0].lon]);
      }
    } catch (error) {
      console.error('Error searching stops:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchArrivals = async (stopId) => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/stops/${stopId}/arrivals`);
      const data = await response.json();
      setArrivals(data);
    } catch (error) {
      console.error('Error fetching arrivals:', error);
      setArrivals([]);
    } finally {
      setLoading(false);
    }
  };

  const handleStopClick = (stop) => {
    setSelectedStop(stop);
    fetchArrivals(stop.stop_id);
    setMapCenter([stop.lat, stop.lon]);
  };

  const formatTime = (minutes) => {
    if (minutes < 1) return 'Arriving';
    if (minutes === 1) return '1 min';
    return `${minutes} mins`;
  };

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-red-600 text-white shadow-lg">
        <div className="container mx-auto px-4 py-4">
          <h1 className="text-3xl font-bold">🚌 OC Transpo Live</h1>
          <p className="text-red-100">Real-time bus tracking for Ottawa</p>
        </div>
      </header>

      <div className="container mx-auto px-4 py-6">
        {/* Search Bar */}
        <div className="mb-6">
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Search by stop name or code..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && searchStops()}
              className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
            />
            <button
              onClick={searchStops}
              className="px-6 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition"
            >
              Search
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Map */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-lg shadow-lg overflow-hidden">
              <MapContainer
                center={mapCenter}
                zoom={13}
                style={{ height: '600px', width: '100%' }}
              >
                <TileLayer
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                />
                
                {/* User location marker */}
                {userLocation && (
                  <Marker position={[userLocation.lat, userLocation.lon]}>
                    <Popup>Your Location</Popup>
                  </Marker>
                )}
                
                {/* Stop markers */}
                {stops.map((stop) => (
                  <Marker
                    key={stop.stop_id}
                    position={[stop.lat, stop.lon]}
                    eventHandlers={{
                      click: () => handleStopClick(stop)
                    }}
                  >
                    <Popup>
                      <div className="text-sm">
                        <strong>{stop.name}</strong>
                        <br />
                        Stop: {stop.code || stop.stop_id}
                      </div>
                    </Popup>
                  </Marker>
                ))}
                
                <MapUpdater center={mapCenter} />
              </MapContainer>
            </div>
          </div>

          {/* Arrivals Panel */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-lg shadow-lg p-6">
              {selectedStop ? (
                <>
                  <h2 className="text-xl font-bold mb-2">{selectedStop.name}</h2>
                  <p className="text-gray-600 mb-4">Stop {selectedStop.code || selectedStop.stop_id}</p>
                  
                  {loading ? (
                    <div className="text-center py-8">
                      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-red-600 mx-auto"></div>
                      <p className="mt-4 text-gray-600">Loading arrivals...</p>
                    </div>
                  ) : arrivals.length > 0 ? (
                    <div className="space-y-3">
                      <h3 className="font-semibold text-gray-700 mb-3">Upcoming Arrivals</h3>
                      {arrivals.map((arrival, index) => (
                        <div
                          key={index}
                          className="border-l-4 border-red-600 bg-gray-50 p-3 rounded"
                        >
                          <div className="flex justify-between items-start">
                            <div>
                              <div className="font-bold text-lg">
                                Route {arrival.route_short_name}
                              </div>
                              <div className="text-sm text-gray-600">
                                {arrival.headsign || arrival.route_long_name}
                              </div>
                              {arrival.is_realtime && (
                                <span className="inline-block mt-1 px-2 py-1 bg-green-100 text-green-800 text-xs rounded">
                                  Live
                                </span>
                              )}
                            </div>
                            <div className="text-right">
                              <div className="text-2xl font-bold text-red-600">
                                {formatTime(arrival.minutes_until_arrival)}
                              </div>
                              {arrival.confidence && (
                                <div className="text-xs text-gray-500">
                                  {Math.round(arrival.confidence * 100)}% confidence
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-gray-500">
                      No upcoming arrivals
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <svg className="w-16 h-16 mx-auto mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  <p>Select a stop on the map to view arrivals</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Stats */}
        <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white rounded-lg shadow p-4">
            <div className="text-sm text-gray-600">Total Stops</div>
            <div className="text-2xl font-bold text-red-600">{stops.length}</div>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <div className="text-sm text-gray-600">Selected Stop</div>
            <div className="text-2xl font-bold text-red-600">
              {selectedStop ? selectedStop.code || '—' : '—'}
            </div>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <div className="text-sm text-gray-600">Active Arrivals</div>
            <div className="text-2xl font-bold text-red-600">{arrivals.length}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Component to update map center
function MapUpdater({ center }) {
  const map = useMap();
  useEffect(() => {
    map.setView(center, map.getZoom());
  }, [center, map]);
  return null;
}

export default App;
