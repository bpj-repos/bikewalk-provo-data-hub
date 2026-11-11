# City crash points, version 1

This local GeoJSON candidate projects the same Utah Crash Data Portal nonmotorist population as the city annual series. It requires the exact state-assigned city, at least one reported motor vehicle, and shared bicycle, pedestrian or other conveyance evidence. Person type codes take precedence over involvement flags. One feature represents one state crash, even when multiple mode flags are true. It adds no police records, inferred matches or geocodes.

Features have stable source-qualified IDs. Properties are allowlisted to source, source_id, city, date, severity, bike, ped and other. The dictionary describes their types. Crash severity and person injury severity are distinct. Unknown crash severity stays Unknown. The event date uses America/Denver and omits time of day. Coordinates are WGS 84 longitude/latitude rounded to four decimal places, approximately 11 meters north/south. The file uses RFC 7946 GeoJSON without a legacy CRS member.

Missing and invalid coordinates are excluded from the map and counted separately. Records outside the requested city, with no reported motor vehicle or with no qualifying mode are also counted separately. Annual statistics can include qualifying crashes without map positions. The manifest binds counts, selected years/date interval, source-workbook SHA-256 and resource hashes. Selected coverage does not establish completeness. Partial and recent records may change.

The workbook remains a private source. The export contains no person names, ages, narratives, agencies, road addresses, exact event times or original raw tables. Its source IDs, dates and approximate locations still identify source events. These are local candidates for analysis. Before sharing real points, review the source's reuse terms, chosen fields and precision for the intended audience. Exporting does not register, approve or publish a Hub release. The manifest and dictionary describe the public interface for a separately reviewed release.

Synthetic demonstration candidates are explicitly marked synthetic and contain invented records. Their geometry, dates and source-like IDs do not describe actual crashes.
