import React, { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, CircleMarker, useMap } from 'react-leaflet';
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

// Blue pulsing dot for user location
const userIcon = L.divIcon({
  className: '',
  html: `<div style="
    width:16px;height:16px;
    background:#2563eb;
    border:3px solid #fff;
    border-radius:50%;
    box-shadow:0 0 0 3px rgba(37,99,235,0.35);
  "></div>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

// Animated bus icon — red, rotates based on bearing
const createBusIcon = (bearing) => L.divIcon({
  className: '',
  html: `
    <div style="transform:rotate(${bearing || 0}deg); width:32px; height:32px;">
      <svg viewBox="0 0 32 32" width="32" height="32" xmlns="http://www.w3.org/2000/svg">
        <polygon points="16,2 22,12 16,9 10,12" fill="#ef4444" opacity="0.9"/>
        <rect x="9" y="10" width="14" height="18" rx="3" fill="#ef4444"/>
        <rect x="11" y="13" width="4" height="4" rx="1" fill="rgba(0,0,0,0.5)"/>
        <rect x="17" y="13" width="4" height="4" rx="1" fill="rgba(0,0,0,0.5)"/>
        <circle cx="11.5" cy="29" r="2" fill="rgba(0,0,0,0.6)"/>
        <circle cx="20.5" cy="29" r="2" fill="rgba(0,0,0,0.6)"/>
      </svg>
    </div>`,
  iconSize: [32, 32],
  iconAnchor: [16, 16],
});

function App() {
  const [selectedStop, setSelectedStop] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [userLocation, setUserLocation] = useState(null);
  const [mapCenter, setMapCenter] = useState([45.4215, -75.6972]);
  const [mapZoom, setMapZoom] = useState(14);

  // Nearby routes (sidebar suggestions)
  const [nearbyRoutes, setNearbyRoutes] = useState([]);
  const [nearbyLoading, setNearbyLoading] = useState(false);

  // Route display state
  const [routeData, setRouteData] = useState(null);
  const [mode, setMode] = useState('nearby'); // 'nearby' | 'route'

  // Live vehicle positions
  const [liveVehicles, setLiveVehicles] = useState([]);
  const [liveError, setLiveError] = useState(false);
  const [direction, setDirection] = useState(0); // 0 or 1

  useEffect(() => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const location = { lat: position.coords.latitude, lon: position.coords.longitude };
          setUserLocation(location);
          setMapCenter([location.lat, location.lon]);
          fetchNearbyRoutes(location.lat, location.lon);
        },
        () => {
          // No location — just show Ottawa center, no routes
        }
      );
    }
  }, []);

  const fetchNearbyRoutes = async (lat, lon) => {    setNearbyLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/nearby-routes?lat=${lat}&lon=${lon}&radius=800&limit=12`);
      setNearbyRoutes(await res.json());
    } catch (e) {
      console.error(e);
    } finally {
      setNearbyLoading(false);
    }
  };

  const searchRoute = async (routeId) => {
    setLoading(true);
    setLiveVehicles([]);
    setLiveError(false);
    setDirection(0);
    try {
      const res = await fetch(`${API_BASE_URL}/routes/${encodeURIComponent(routeId)}/stops`);
      if (!res.ok) return false;
      const data = await res.json();
      setRouteData(data);
      setMode('route');
      setSelectedStop(null);
      // Fit map to route bounds
      if (data.stops.length > 0) {
        const lats = data.stops.map(s => s.stop_lat);
        const lons = data.stops.map(s => s.stop_lon);
        const centerLat = (Math.min(...lats) + Math.max(...lats)) / 2;
        const centerLon = (Math.min(...lons) + Math.max(...lons)) / 2;
        setMapCenter([centerLat, centerLon]);
        setMapZoom(13);
      }
      return true;
    } catch (e) {
      console.error(e);
      return false;
    } finally {
      setLoading(false);
    }
  };

  // Poll live vehicle positions every 15 s while a route is displayed
  useEffect(() => {
    if (mode !== 'route' || !routeData) return;

    const fetchVehicles = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/routes/${encodeURIComponent(routeData.route_id)}/vehicles`);
        if (!res.ok) { setLiveError(true); return; }
        const data = await res.json();
        setLiveVehicles(data);
        setLiveError(false);
      } catch {
        setLiveError(true);
      }
    };

    fetchVehicles();                        // immediate first call
    const timer = setInterval(fetchVehicles, 15000);
    return () => clearInterval(timer);
  }, [mode, routeData]);

  const handleSearch = async () => {
    const q = searchQuery.trim();
    if (!q) {
      setMode('nearby');
      setRouteData(null);
      return;
    }
    await searchRoute(q);
  };

  const handleStopClick = (stop) => {
    setSelectedStop(stop);
    setMapCenter([stop.stop_lat, stop.stop_lon]);
  };

  const lineColor = routeData?.route_color ? `#${routeData.route_color}` : '#e53e3e';

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="bg-gray-950 border-b border-gray-800 px-6 py-4 flex items-center gap-4">
        <h1 className="text-xl font-bold tracking-tight">🚌 OC Transpo Live</h1>
        <div className="flex-1 flex gap-2 max-w-md">
          <input
            type="text"
            placeholder='Route number or stop name…'
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-white placeholder-gray-500"
          />
          <button
            onClick={handleSearch}
            disabled={loading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium transition disabled:opacity-50"
          >
            {loading ? '…' : 'Go'}
          </button>
          {mode === 'route' && (
            <button
              onClick={() => { setMode('nearby'); setRouteData(null); setSelectedStop(null); setSearchQuery(''); }}
              className="px-3 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600 text-sm transition"
            >
              ✕
            </button>
          )}
        </div>
      </header>

      <div className="flex h-[calc(100vh-64px)]">
        {/* Sidebar */}
        <div className="w-80 shrink-0 bg-gray-900 border-r border-gray-800 overflow-y-auto">

          {/* ── NEARBY ROUTES ── */}
          {mode === 'nearby' && (
            <div className="p-4">
              <div className="text-xs text-gray-500 uppercase tracking-widest mb-3">
                {userLocation ? 'Routes near you' : 'Waiting for location…'}
              </div>

              {nearbyLoading ? (
                <div className="flex items-center gap-2 text-gray-400 py-4">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500"></div>
                  <span className="text-sm">Finding nearby routes…</span>
                </div>
              ) : nearbyRoutes.length === 0 && userLocation ? (
                <p className="text-sm text-gray-500">No routes found within 800 m.</p>
              ) : (
                <div className="space-y-2">
                  {nearbyRoutes.map((r) => {
                    const color = r.route_color ? `#${r.route_color}` : '#e53e3e';
                    return (
                      <button
                        key={r.route_id}
                        onClick={() => searchRoute(r.route_id)}
                        className="w-full flex items-center gap-3 p-3 rounded-lg bg-gray-800 hover:bg-gray-700 transition text-left"
                      >
                        <div
                          className="shrink-0 w-10 h-10 rounded-lg flex items-center justify-center font-bold text-sm"
                          style={{ backgroundColor: color, color: r.route_text_color ? `#${r.route_text_color}` : '#fff' }}
                        >
                          {r.route_id}
                        </div>
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-white truncate">{r.name}</div>
                          <div className="text-xs text-gray-400 truncate">
                            {r.nearest_stop} · {r.nearest_m < 1000 ? `${r.nearest_m} m` : `${(r.nearest_m / 1000).toFixed(1)} km`}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ── ROUTE DETAIL ── */}
          {mode === 'route' && routeData && (
            <div>
              {/* Route header */}
              <div className="p-4 border-b border-gray-800" style={{ borderLeftWidth: 4, borderLeftColor: lineColor }}>
                <div className="flex items-center gap-3 mb-1">
                  <div
                    className="w-12 h-12 rounded-lg flex items-center justify-center font-bold text-lg"
                    style={{ backgroundColor: lineColor }}
                  >
                    {routeData.route_id}
                  </div>
                  <div>
                    <div className="font-semibold text-white">{routeData.name}</div>
                    {routeData.trip_headsign && (
                      <div className="text-xs text-gray-400">→ {routeData.trip_headsign}</div>
                    )}
                  </div>
                </div>
                <div className="text-xs text-gray-500">{routeData.stops.length} stops
                {liveVehicles.length > 0 && (
                  <span className="ml-2 text-green-400">● {liveVehicles.filter(v => (v.direction_id ?? 1) === direction).length} live</span>
                )}
                {liveError && (
                  <span className="ml-2 text-yellow-500">⚠ no live data</span>
                )}
              </div>
              {/* Direction toggle */}
              <div className="flex gap-1 mt-2">
                <button
                  onClick={() => setDirection(0)}
                  className={`flex-1 py-1 text-xs rounded font-medium transition ${
                    direction === 0 ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                  }`}
                >
                  → Outbound
                </button>
                <button
                  onClick={() => setDirection(1)}
                  className={`flex-1 py-1 text-xs rounded font-medium transition ${
                    direction === 1 ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                  }`}
                >
                  ← Inbound
                </button>
              </div>
              </div>

              {/* Selected stop */}
              {selectedStop && (
                <div className="p-4 border-b border-gray-800 bg-gray-800">
                  <div className="text-xs text-gray-400 mb-1">Selected stop</div>
                  <div className="font-medium text-white">{selectedStop.name}</div>
                  <div className="text-xs text-gray-500">#{selectedStop.stop_id}</div>
                  {selectedStop.arrival_time && (
                    <div className="text-xs text-blue-400 mt-1">🕐 {selectedStop.arrival_time}</div>
                  )}
                </div>
              )}

              {/* Stop list */}
              <div>
                {routeData.stops.map((stop, i) => (
                  <button
                    key={stop.stop_id}
                    onClick={() => handleStopClick(stop)}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-gray-800 transition ${
                      selectedStop?.stop_id === stop.stop_id ? 'bg-gray-800' : ''
                    }`}
                  >
                    <span className="text-xs text-gray-600 w-5 text-right shrink-0">{i + 1}</span>
                    <div
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ backgroundColor: lineColor }}
                    />
                    <div className="min-w-0">
                      <div className="text-sm text-gray-200 truncate">{stop.name}</div>
                      {stop.arrival_time && (
                        <div className="text-xs text-gray-500">{stop.arrival_time}</div>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Map */}
        <div className="flex-1">
          <MapContainer
            center={mapCenter}
            zoom={mapZoom}
            style={{ height: '100%', width: '100%' }}
            zoomControl={false}
          >
            <TileLayer
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              attribution='&copy; <a href="https://carto.com/">CARTO</a>'
            />

            {/* User location blue dot */}
            {userLocation && (
              <Marker position={[userLocation.lat, userLocation.lon]} icon={userIcon}>
                <Popup>You are here</Popup>
              </Marker>
            )}

            {/* Route polyline + stops */}
            {mode === 'route' && routeData && (
              <>
                <Polyline
                  positions={routeData.shape?.length > 0
                    ? routeData.shape
                    : routeData.stops.map(s => [s.stop_lat, s.stop_lon])}
                  color={lineColor}
                  weight={4}
                  opacity={0.9}
                />
                {routeData.stops.map((stop) => (
                  <CircleMarker
                    key={stop.stop_id}
                    center={[stop.stop_lat, stop.stop_lon]}
                    radius={selectedStop?.stop_id === stop.stop_id ? 8 : 5}
                    color={lineColor}
                    fillColor={selectedStop?.stop_id === stop.stop_id ? lineColor : '#1f2937'}
                    fillOpacity={1}
                    weight={2}
                    eventHandlers={{ click: () => handleStopClick(stop) }}
                  >
                    <Popup>
                      <div className="text-sm">
                        <strong>{stop.name}</strong><br />
                        Stop #{stop.stop_id}<br />
                        {stop.arrival_time && <>🕐 {stop.arrival_time}</>}
                      </div>
                    </Popup>
                  </CircleMarker>
                ))}

                {/* Live bus markers — filtered by direction */}
                {liveVehicles
                  .filter(v => (v.direction_id ?? 1) === direction)
                  .map((v) => (
                  <Marker
                    key={v.vehicle_id}
                    position={[v.lat, v.lon]}
                    icon={createBusIcon(v.bearing)}
                    zIndexOffset={1000}
                  >
                    <Popup>
                      <div className="text-sm">
                        <strong>Bus {v.label}</strong><br />
                        {v.speed_kmh != null && <>Speed: {v.speed_kmh} km/h<br /></>}
                        {v.bearing != null && <>Bearing: {Math.round(v.bearing)}°<br /></>}
                        Status: {v.status}<br />
                        Trip: {v.trip_id}
                      </div>
                    </Popup>
                  </Marker>
                ))}
              </>
            )}

            <MapUpdater center={mapCenter} zoom={mapZoom} />
          </MapContainer>
        </div>
      </div>
    </div>
  );
}

function MapUpdater({ center, zoom }) {
  const map = useMap();
  useEffect(() => {
    map.setView(center, zoom);
  }, [center, zoom, map]);
  return null;
}

export default App;
