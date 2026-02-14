import { memo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import { Users, ArrowUpRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import 'leaflet/dist/leaflet.css'

interface GeoCityUser {
  uuid: string
  username: string | null
  status: string
  connections: number
}

interface GeoCity {
  city: string
  country: string
  lat: number
  lon: number
  count: number
  unique_users: number
  users?: GeoCityUser[]
}

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: 'bg-green-500/20 text-green-400',
  DISABLED: 'bg-red-500/20 text-red-400',
  EXPIRED: 'bg-yellow-500/20 text-yellow-400',
  LIMITED: 'bg-orange-500/20 text-orange-400',
}

interface LazyGeoMapProps {
  cities: GeoCity[]
  maxCount: number
  center: [number, number]
  mapBackground: string
  mapTileUrl: string
}

const LazyGeoMap = memo(function LazyGeoMap({
  cities,
  maxCount,
  center,
  mapBackground,
  mapTileUrl,
}: LazyGeoMapProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  return (
    <MapContainer
      center={center}
      zoom={3}
      className="h-full w-full"
      style={{ background: mapBackground }}
      attributionControl={false}
    >
      <TileLayer url={mapTileUrl} />
      <MarkerClusterGroup
        chunkedLoading
        maxClusterRadius={40}
        spiderfyOnMaxZoom
        showCoverageOnHover={false}
      >
        {cities.map((city: GeoCity, idx: number) => {
          const radius = Math.max(5, Math.min(25, (city.count / maxCount) * 25))
          const users = city.users || []
          return (
            <CircleMarker
              key={`${city.city}-${city.country}-${idx}`}
              center={[city.lat, city.lon]}
              radius={radius}
              pathOptions={{
                color: '#06b6d4',
                fillColor: '#22d3ee',
                fillOpacity: 0.4,
                weight: 1,
              }}
            >
              <Popup>
                <div className="text-xs min-w-[200px]">
                  <p className="font-semibold text-sm mb-1">{city.city}, {city.country}</p>
                  <p className="text-muted-foreground mb-2">
                    {t('analytics.geo.connections', { count: city.count })}
                    {city.unique_users > 0 && (
                      <> · {t('analytics.geo.uniqueUsers', { count: city.unique_users })}</>
                    )}
                  </p>
                  {users.length > 0 && (
                    <div className="border-t border-border/50 pt-1.5 space-y-1">
                      {users.map((u: GeoCityUser) => (
                        <div
                          key={u.uuid}
                          className="flex items-center justify-between gap-2 px-1 py-0.5 rounded hover:bg-accent/50 cursor-pointer"
                          onClick={(e) => {
                            e.stopPropagation()
                            navigate(`/users/${u.uuid}`)
                          }}
                        >
                          <div className="flex items-center gap-1.5 min-w-0">
                            <Users className="w-3 h-3 shrink-0 text-muted-foreground" />
                            <span className="truncate max-w-[120px] text-primary hover:underline">
                              {u.username || u.uuid.slice(0, 8)}
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5 shrink-0">
                            <Badge
                              variant="secondary"
                              className={cn('text-[10px] px-1 py-0', STATUS_COLORS[u.status] || '')}
                            >
                              {t(`analytics.status.${u.status}`, { defaultValue: u.status })}
                            </Badge>
                            <ArrowUpRight className="w-3 h-3 text-muted-foreground" />
                          </div>
                        </div>
                      ))}
                      {city.unique_users > users.length && (
                        <p className="text-[10px] text-muted-foreground text-center pt-0.5">
                          {t('analytics.geo.andMore', { count: city.unique_users - users.length })}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </Popup>
            </CircleMarker>
          )
        })}
      </MarkerClusterGroup>
    </MapContainer>
  )
})

export default LazyGeoMap
