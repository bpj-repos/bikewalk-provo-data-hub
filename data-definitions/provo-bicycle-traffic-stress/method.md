# Provo bicycle traffic stress 1.0.0

BikeWalk reconciles published traffic-stress observations and runs the pinned Brokenspoke result as a gap fill. Geometry, eligibility, native scores, disagreement and selection reasons remain inspectable. These estimates describe modeled bicycling comfort. Field conditions and project design require independent verification.

## Population and geometry

The reference network is the November 7, 2026 Geofabrik Utah OpenStreetMap extract. The source receipt fingerprints the retained extraction containing original OSM node IDs, ways and tags. The extraction recipe and original PBF remain in the private input archive. Clip ways to the captured Provo municipal polygon, including holes. Public named service streets and alleys enter the reference. Parking aisles, driveways, unnamed service ways, conditional access, and pedestrian ways without affirmative bicycle access are counted separately. Explicit bicycle or access prohibitions exclude a way. Bicycle-specific permissions supersede general access. Main coverage includes paths open to bicycles regardless of paving. Surfaces and trail use need consideration when interpreting traffic stress.

Use shared OSM nodes for topology. A geometric intersection of a bridge and the road beneath it creates no junction. An incoming approach is an allowed bicycle movement toward a shared node with three or more distinct eligible neighbors. Degree-two segmentation points and dead ends contribute no approach records. Published BNA junctions with at least three source arms also retain their incoming approaches where no reference junction lies within two meters. These carry source_network eligibility, native incoming-segment identities and connecting-road context. Their counts are reported separately from the OSM reference denominator. This is an approach inventory, without individual outgoing turn movements. Source one-way bicycle restrictions suppress unavailable ratings. OSM tags establish eligible travel directions independently.

Street geometry from Provo and SGID is independently captured using all IDs in the municipal envelope, with membership and edit-state checks. Additional city portions with an explicit public owner enter the inventory at unspecified direction scope. Published PFB portions absent from the reference geometry screen retain native directional selections with source_network eligibility and separately reported direction-length. Other additional linework is retained in supplemental-inventory.geojson for access and identity review. These supplemental sources overlap one another. Their summed mileage cannot be added to the reference denominator. Crosswalk and UDOT study inputs are retained privately for the pilot and identified by checksum in sources.json.

Within each topological way part, evaluate intervals no longer than five meters in UTM 12N. A rating candidate must be within eight meters, project to the source interior and align within about thirty degrees. Rank distance plus six times alignment penalty, requiring a three-meter lead over the runner-up. BNA candidates must also share the original OSM way ID. Group adjacent equal matches. A split or renumbered OSM ID may lose a historical BNA match and be filled from the local model or Utah. Source matching boundaries are approximate to five meters. Reject Utah directional matching on tagged bridges, tunnels and nonzero OSM layers because the Utah export omits grade. Compatible road/path identity is required. For supplemental geometry, twelve-meter aligned overlap is a screening criterion, subject to review around parallel facilities.

## Selecting observations

Retain every matched native observation, including inapplicable whole-line observations. For a direction with both published sources, a sole documented decisive-input evidence record wins. That record must identify feature, source, native record ID, attribute, observation date, reference and whether the competing value was defaulted or older. Equal or mixed evidence selects PeopleForBikes with published_directional_tiebreak. A later retrieval or service edit date alone is insufficient evidence. The first receipt contains no claimed decisive-input overrides.

A sole applicable published source wins. Published PeopleForBikes or Utah observations precede a locally run model. The local Brokenspoke result fills remaining applicable directions and approaches. Every eligible feature with an applicable score gets a selection even when bands disagree. Missing observations remain null with no_applicable_rating and geometry match reasons. A conflict never suppresses an otherwise applicable observation.

Utah publishes one score using its ranked primary facility. On asymmetric facilities that score is retained at unspecified direction scope. It cannot be transferred to both travel directions. A trail or equal facility on both sides can supply a directional fallback. Whole-line observations count toward physical coverage and remain distinguishable from verified directional coverage. Utah lines supply no crossing score.

The receiving endpoint of the BNA forward direction carries ft_int_stress. The reverse direction carries tf_int_stress at the opposite endpoint. Match incoming geometry within two meters of that endpoint and within thirty degrees of its incoming bearing. Only actual reference-network junctions enter approaches.geojson. When a model has no corresponding endpoint, its segment score supplies no crossing rating.

Broad rendering bands are lower for native scores 0–2 and higher for 3–4, preserving the source scale. Published Provo 26.04 contains 1 and 3. Utah 0 is a valid rating. A higher score from one scale cannot be used to rank accuracy against a number on another scale. Preserve speed and directional lanes as nullable source fields. No value is filled from a rating and total lanes are never divided by two. Local model exports omit these measurements, so they remain unavailable for those observations.

## Published methods and the pilot

PeopleForBikes BNA targets low-stress connectivity for the interested-but-concerned rider. It rates directions and incoming approaches using OSM infrastructure, speed, lanes, width, parking and controls, with documented class defaults when fields are missing. Published 26.04 precedes the November 7 reference and November 8 local model OSM snapshots. The exact production analyzer revision for 26.04 is unverified. The local result is Brokenspoke 3.3.0, digest-pinned in the Safe Routes receipt, with 25 mph residential model default. It is labeled bikewalk-brokenspoke. Existing local results use original OSM inputs and model defaults. The pilot does not claim that local street attributes were injected into this already-executed model.

Utah Bikeways is the UGRC existing-network product linked from UDOT UPlan. It uses facility, cartographic road class, speed and AADT. Native scores span 0–4. The reference publisher script ranks the better facility first, uses AADT2023 and maps missing volume to a negative sentinel that can enter a low-volume branch. Its dissolved public output omits decisive speed and volume fields and original road identities. The script revision actually used for the October 9 layer is unverified. This limits automatic evidence precedence despite a populated score.

Mekuria–Furth–Nixon 2012 LTS distinguishes segments, intersection approaches and unsignalized crossings, using published ordinal criteria and weakest-link logic. Physical separation, speed, width, lanes, volume, centerlines and crossing refuge affect different tables. The retained first-edition Table 6 defines the optional Furth crossing evaluator. It requires crossed-street speed, total crossed lanes and an explicitly known refuge-island status. Unknown input produces no rating. It is restricted to unsignalized crossings without a conflicting or unsupported control configuration. Later criteria, including version 2.2 segment criteria and draft roundabout criteria, require their own version-specific assessment. This release applies no Furth scores to city movements without complete movement-specific inputs.

Bicycle level of service (NCHRP Web-Only Document 128 / HCM family) is an additional research comparison for detailed corridors. Its perceived-service formulation and inputs have a different outcome and scale. No numerical conversion to LTS is made. Published validation of LTS methods is mixed and methods disagree. Source agreement is a reproducibility check, not independent rider validation.

Pilot cases are generated in pilot.json from the 800 North / 500 West signal 6444, the nonsignalized study, trail junctions, asymmetric facilities, divided roads, bridges and service geometry. UDOT study records and nearby crosswalk lines corroborate local features. Their point proximity does not establish lane orientation, control of a bicycle movement or a refuge island. Report BNA/local disagreement and missing method inputs. A later field or source verification can populate dated evidence without changing thresholds. No independent rider assessment has been completed in this release.

## Attribution and reuse

© OpenStreetMap contributors, https://www.openstreetmap.org/copyright. The OSM-derived database is available under ODbL 1.0, https://opendatacommons.org/licenses/odbl/1-0/. BikeWalk processing is identified as a modification. PeopleForBikes provides BNA results and Brokenspoke software. Utah Geospatial Resource Center / Utah Bikeways and Utah Roads are attributed under CC BY 4.0. Retain original source identities and identify the derived reconciliation. Provo City and UDOT inventories retain their informational-use and accuracy notices. Raw local inventories remain private; the public package includes minimized derived geometry and no staff attribution, address ranges or operational fields.

## Primary references

- PeopleForBikes methodology https://cityratings.peopleforbikes.org/about/methodology
- 2026 changes https://www.peopleforbikes.org/news/2026-city-ratings-methodology
- Brokenspoke 3.3.0 https://peopleforbikes.github.io/brokenspoke-analyzer/
- Field directions https://peopleforbikes.github.io/brokenspoke-analyzer/shapefile-data-dictionary.html
- UGRC source https://gis.utah.gov/products/sgid/transportation/bikeways/
- Utah method https://docs.google.com/document/d/1eo9BscAbXFHKlw8EONFRi4lntBwvON8JzV6tN2D_j6I/edit
- Publisher code https://github.com/agrc/wfrc-bike-map/blob/main/scripts/update-bikeways.py
- Furth original criteria https://peterfurth.sites.northeastern.edu/wp-content/uploads/2014/05/LTS-Tables1.pdf
- Furth commentary https://peterfurth.sites.northeastern.edu/level-of-traffic-stress/
- Original research https://rosap.ntl.bts.gov/view/dot/24453/dot_24453_DS1.pdf
- NCHRP comparison https://nacto.org/wp-content/uploads/nchrp_w128_MLOS_UsersGuide.pdf
- Method/data comparison https://www.sciencedirect.com/science/article/pii/S2210670723007606
- Behavioral validation https://www.sciencedirect.com/science/article/abs/pii/S0966692316304616
