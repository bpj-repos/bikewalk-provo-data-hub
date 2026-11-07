import unittest
from danger_zones.motor_vehicle_candidate import classify


def case(body="Truck Tractor"):
    return {"crash": {"numberOfVehicles": "1", "cyclist_involved": None, "pedestrian_involved": None},
            "persons": [{"vehicleNumber": "1", "personType": "1", "personType_label": "Driver"}],
            "vehicles": [{"vehicleNumber": "1", "vehicleBodyType_label": body}],
            "rollups": [{"cyclist_involved": "N", "pedestrian_involved": "N"}]}


class MotorVehicleTests(unittest.TestCase):
    def test_includes_single_truck_and_motorcycle_with_reported_driver(self):
        for body in ("Truck Tractor", "Motorcycle (2 wheels)"):
            with self.subTest(body=body):
                self.assertEqual(classify(case(body))[0], "included")

    def test_nonmotorists_excluded_even_if_flags_miss_other_conveyance(self):
        for code, label in [("3", "Pedestrian"), ("4", "Pedalcyclist"),
                            ("5", "Other Pedestrian (wheelchair, skater, personal conveyance, etc.)")]:
            m = case()
            m["persons"].append({"personType": code, "personType_label": label, "vehicleNumber": None})
            self.assertEqual(classify(m)[0], "excluded")

    def test_missing_and_conflicting_records_stay_unresolved(self):
        for mutation in [lambda m: m.update(persons=[]), lambda m: m.update(rollups=[]),
                         lambda m: m["persons"][0].update(vehicleNumber="2"),
                         lambda m: m["persons"][0].update(personType_label="Unknown"),
                         lambda m: m["crash"].update(cyclist_involved="Y"),
                         lambda m: m["rollups"][0].update(pedestrian_involved="Y")]:
            m = case()
            mutation(m)
            self.assertEqual(classify(m)[0], "unresolved")
