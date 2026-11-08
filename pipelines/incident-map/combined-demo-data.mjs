import assert from "node:assert/strict";

// Explicit public-field list. New provider fields require a publication review.
export const udotFields = new Set(`AGGRESSIVE_DRIVING BICYCLIST_INVOLVED COLLISION_WITH_FIXED_OBJECT COMMERCIAL_MOTOR_VEH_INVOLVED COUNTY_NAME CRASH_DATETIME CRASH_ID CRASH_SEVERITY_DESC CURRENT_AS_OF_DATE DEBRIS DISREGARD_TRAFFIC_CONTROL_DEV DISTRACTED_DRIVING DIVIDED_HIGHWAY DOMESTIC_ANIMAL_RELATED DROWSY_DRIVING DUI ERR_CD EXIT_NUMBER FIRST_HARMFUL_EVENT_DESC FUNCTIONAL_CLASS HIT_AND_RUN HORIZONTAL_ALIGNMENT_DESC IMPROPER_RESTRAINT IMPROPER_RESTRAINT_FATAL_TOT IMPROPER_RESTRAINT_LEVEL4_TOT LIGHT_CONDITION_DESC LOCATION_DESC MAIN_ROAD_NAME MANNER_COLLISION_DESC MOTORCYCLE_INVOLVED MOTOR_CARRIER_INVOLVED_YN NUMBER_FATALITIES NUMBER_FOUR_INJURIES NUMBER_ONE_INJURIES NUMBER_THREE_INJURIES NUMBER_TWO_INJURIES NUMBER_VEHICLES_INVOLVED OBJECTID OLDER_DRIVER_INVOLVED OVERTURN_ROLLOVER PAVEMENT_DESC PEDESTRIAN_INVOLVED RAILROAD_CROSSING RAMP_ID REGION_NAME ROADWAY_CONTRIB_CIRCUM_DESC ROADWAY_DEPARTURE ROADWAY_JUNCT_FEATURE_DESC ROADWAY_SURF_CONDITION_DESC ROADWAY_TYPE_CD ROAD_JURISDICTION_DESC ROUTE ROUTE_DIRECTION SINGLE_VEHICLE SPEED_RELATED START_ACCUM TEENAGE_DRIVER_INVOLVED TRAIN_INVOLVED TRANSIT_VEHICLE_INVOLVED UNRESTRAINED UNRESTRAINED_FATAL_TOT UNRESTRAINED_LEVEL4_TOT VERTICAL_ALIGNMENT_DESC WEATHER_CONDITION_DESC WILD_ANIMAL_RELATED WORK_ZONE_RELATED_YNU`.split(" "));
export const policeFields = new Set([
  "Case number", "Date of report", "Original travel mode", "Original location", "Normalized address", "Location note",
  "Event type", "Severity", "Location match status", "Location match method", "Location match provider",
  "Location match confidence", "Location match label", "Source conflict", "Source version count",
  "Source snapshots", "Source sheets", "Source tables", "Source rows", "Retrieved at",
]);
export const provenanceFields = new Set(["Source snapshot", "Retrieved at", "Checked at", "Source current through", "Identity evidence"]);

const portalFields = new Set(`Crash_ID crashDateandTime County City_Geo latitude longitude route direction type milePoint exitNumber rampID roadName crashSeverity mannerCollision roadwayContributingCircumstances weatherCondition lightCondition roadwaySurfaceCondition roadwayJunction firstHarmfulEvent workZoneRelated numberOfVehicles functional UR holiday pedestrian_involved motorcycle_involved speed_related wrong_way_driving aggressive_driving animal_related hit_and_run teenage_driver_involved older_driver_involved adverse_weather alcohol_confirmed alcohol_suspected cyclist_involved drugs_confirmed drugs_suspected dui single_vehicle unrestrained officer_department distracted_driving drowsy_driving crash_date crash_mins county countyName city_geo mile_point exit_number crashSeverity_label mannerCollision_label roadwayContribCircumstances_label roadwayContribCircumstances2_label roadwayJunction_label firstHarmfulEvent_label Source snapshot Source checked at Join evidence`.split(" "));
const portalExtraFields = new Set(["Source snapshot", "Source checked at", "Join evidence", "Classifications"]);
const rollupFields = new Set("alcohol_suspected drugs_suspected unrestrained roadway_departure older_driver_involved adverse_roadway_surf_condition dui aggressive_driving disregard_traffic_control_dev distracted_driving drowsy_driving speed_related motorcycle_involved cyclist_involved pedestrian_involved intersection_related adverse_weather roadway_geometry_related wild_animal_related domestic_animal_related animal_related overturn_rollover commercial_motor_veh_involved heavy_truck_involved interstate_highway teenage_driver_involved urban_county night_dark_condition single_vehicle train_involved railroad_crossing transit_vehicle_involved right_turn_involved left_or_u_turn_involved wrong_way_driving work_zone_involved divided_highway hit_and_run debris alcohol_confirmed drugs_confirmed".split(" "));
const personFields = new Set("vehicleNumber personType ageCalculated sex injuryLevel personDriverContribCircumstances1 personDriverContribCircumstances2 personNmContribCircumstances personNmLocation personType_label injuryLevel_label personDriverContribCircumstances1_label personDriverContribCircumstances2_label personNmContribCircumstances_label personNmLocation_label".split(" "));
const vehicleFields = new Set("vehicleNumber vehicleBodyType vehicleManeuver mostHarmfulEvent specialFunction vehicleBodyType_label vehicleManeuver_label mostHarmfulEvent_label specialFunction_label".split(" "));

export function validateDetails(details) {
  assert.ok(details && typeof details === "object" && !Array.isArray(details));
  for (const [key, value] of Object.entries(details)) {
    const [source, field] = key.split(": ");
    assert.equal(key, source + ": " + field);
    assert.ok((source === "Police" && policeFields.has(field)) || (source === "UDOT" && udotFields.has(field)) || (source === "Provenance" && provenanceFields.has(field)) || (source === "Portal" && (portalFields.has(field) || portalExtraFields.has(field) || /^(Person|Vehicle) [1-9][0-9]{0,3}$/.test(field))), `Unapproved detail: ${key}`);
    assert.ok(value === null || typeof value === "string" || typeof value === "boolean" || (typeof value === "number" && Number.isFinite(value)));
    if (typeof value === "string") assert.ok(value.length <= 16000);
  }
}

