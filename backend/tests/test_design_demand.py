from modules.roads.design.demand import Demand, build_demand, pcu_of_row

F = {"cars": 1.0, "two_wheelers": 0.5, "autos": 0.8, "buses": 3.0, "trucks": 3.0, "cycles": 0.4}


def test_pcu_from_vehicle_types_uses_the_conversion_factors():
    assert pcu_of_row({"cars": 100, "two_wheelers": 200, "buses": 10}, F) == 100 + 100 + 30


def test_pcu_falls_back_to_total_vehicles_when_no_types():
    assert pcu_of_row({"total_vehicles": 5000}, F) == 5000


def test_types_win_over_total_and_missing_values_are_skipped():
    assert pcu_of_row({"cars": 10, "buses": None, "total_vehicles": 9999}, F) == 10


def test_row_with_no_numbers_has_no_pcu():
    assert pcu_of_row({"road_name": "x"}, F) is None
    assert pcu_of_row({"cars": "lots"}, F) is None


def test_no_rows_no_demand():
    assert build_demand([], [], [], F) == Demand()


def test_peak_is_the_highest_traffic_row_with_a_source_note():
    rows = [{"row_no": 4, "cars": 100, "is_sample": True, "time_period": "8-9 AM"},
            {"row_no": 9, "cars": 900, "is_sample": True, "time_period": "6-7 PM"},
            {"row_no": 5, "cars": 300}]
    d = build_demand(rows, [], [], F)
    assert d.peak_pcu == 900
    assert "row 9" in d.pcu_detail and "SAMPLE" in d.pcu_detail and "6-7 PM" in d.pcu_detail and "3 traffic counts" in d.pcu_detail


def test_real_rows_are_not_labelled_sample():
    d = build_demand([{"row_no": 2, "cars": 50}], [], [], F)
    assert "SAMPLE" not in d.pcu_detail and "1 traffic count " in d.pcu_detail


def test_peak_pedestrians_and_bus_stops():
    d = build_demand([], [{"row_no": 3, "pedestrians": 400, "is_sample": True}, {"row_no": 4, "pedestrians": 900}],
                     [{"is_sample": True}, {}], F)
    assert d.peak_pedestrians == 900 and "row 4" in d.ped_detail and "peak-hour" in d.ped_detail
    assert d.bus_stops == 2 and "SAMPLE" in d.bus_detail


def test_bad_pedestrian_values_are_ignored():
    assert build_demand([], [{"pedestrians": "many"}], [], F).peak_pedestrians is None
