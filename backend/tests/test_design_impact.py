from modules.roads.design import engine, impact

CFG = engine.load_config()


def test_sample_demand_is_labelled_as_sample_and_scales_with_capacity():
    pcu, detail = impact.sample_demand_pcu("secondary", CFG)
    assert pcu == 2 * 1200 * 0.75  # secondary dir_default=2, lane_capacity=1200, load=0.75
    assert "SAMPLE DATA" in detail and "secondary" in detail


def test_estimate_is_marked_sample_data_throughout():
    current = engine.current_state(1200)  # 12 m road
    result = impact.estimate(current_elements=current["elements"], option_lanes=2, oneway=False,
                             length_m=500, road_class="secondary", cfg=CFG)
    assert result["sample_data"] is True
    assert "SAMPLE" in result["note"] and "SUMO" in result["note"]
    assert "SAMPLE" in result["sample_pcu_detail"]
    assert result["length_m"] == 500


def test_fewer_lanes_after_means_more_minutes_and_positive_change():
    current = engine.current_state(2000)  # wide road -> several inferred "before" lanes
    before_many_lanes = impact.estimate(current_elements=current["elements"], option_lanes=2, oneway=False,
                                        length_m=1000, road_class="secondary", cfg=CFG)
    assert before_many_lanes["before"]["lanes"] > before_many_lanes["after"]["lanes"]
    assert before_many_lanes["after"]["minutes"] >= before_many_lanes["before"]["minutes"]
    assert before_many_lanes["change_pct"] >= 0


def test_narrow_road_has_no_footpath_in_current_state_but_still_estimates():
    current = engine.current_state(400)  # 4 m: too narrow for engine.current_state's notional footpath
    assert all(e["kind"] == "carriageway" for e in current["elements"])
    result = impact.estimate(current_elements=current["elements"], option_lanes=1, oneway=False,
                             length_m=200, road_class="residential", cfg=CFG)
    assert result["before"]["lanes"] >= 1


def test_zero_or_missing_length_falls_back_to_a_placeholder_stretch():
    current = engine.current_state(1200)
    result = impact.estimate(current_elements=current["elements"], option_lanes=2, oneway=False,
                             length_m=None, road_class="secondary", cfg=CFG)
    assert result["length_m"] == 100.0


def test_inferred_lane_count_is_capped_at_a_sane_maximum():
    current = engine.current_state(15000)  # absurdly wide notional carriageway
    result = impact.estimate(current_elements=current["elements"], option_lanes=4, oneway=False,
                             length_m=500, road_class="primary", cfg=CFG)
    assert result["before"]["lanes"] <= impact.MAX_INFERRED_LANES
