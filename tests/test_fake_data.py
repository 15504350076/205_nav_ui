"""单元测试模块：覆盖 fake_data 相关逻辑与边界行为。"""

from fake_data import FakeDataGenerator


def test_initial_data_has_truth_fields_and_online_state() -> None:
    generator = FakeDataGenerator()

    initial = generator.get_initial_data()

    assert len(initial) == len(generator.platforms)
    assert all(item.is_online for item in initial)
    assert all(item.truth_x is not None for item in initial)
    assert all(item.truth_y is not None for item in initial)
    assert all(item.truth_z is not None for item in initial)


def test_next_frame_timestamp_advances_and_ids_are_unique() -> None:
    generator = FakeDataGenerator()

    frame = generator.get_next_frame()

    assert frame
    assert all(item.timestamp > 0.0 for item in frame)
    frame_ids = [item.id for item in frame]
    assert len(frame_ids) == len(set(frame_ids))


def test_packet_loss_keeps_at_least_one_platform_in_frame() -> None:
    generator = FakeDataGenerator()
    generator.set_packet_loss_enabled(True)
    generator.set_packet_loss_rate(0.95)

    frame = generator.get_next_frame()

    assert len(frame) >= 1
