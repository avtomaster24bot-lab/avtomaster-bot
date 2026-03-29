from aiogram.fsm.state import State, StatesGroup

class StationAdminStates(StatesGroup):
    entering_request_id = State()
    choosing_new_status = State()
    entering_amount = State()
    choosing_category_action = State()
    choosing_category_to_add = State()
    choosing_category_to_remove = State()
    waiting_for_price_file = State()

class WashAdminStates(StatesGroup):
    choosing_setting = State()
    entering_boxes = State()
    entering_duration = State()
    entering_hours = State()
    waiting_for_days = State()

class TowAdminStates(StatesGroup):
    entering_price = State()
    entering_tow_request_id = State()
    choosing_tow_status = State()

class RegionalAdminStates(StatesGroup):
    adding_station_name = State()
    adding_station_address = State()
    adding_station_phone = State()
    adding_station_admin = State()
    adding_wash_name = State()
    adding_wash_address = State()
    adding_wash_phone = State()
    adding_wash_boxes = State()
    adding_wash_duration = State()
    adding_wash_admin = State()
    adding_tow_name = State()
    adding_tow_phone = State()
    adding_tow_admin = State()
    adding_supplier_name = State()
    adding_supplier_type = State()
    adding_supplier_address = State()
    adding_supplier_phone = State()
    adding_supplier_location = State()
    adding_supplier_admin = State()
    editing_priority = State()
    adding_urgent_name = State()
    adding_urgent_service_type = State()
    adding_urgent_phone = State()
    adding_urgent_address = State()
    adding_urgent_admin = State()
    viewing_request = State()
    choosing_station_for_price = State()
    waiting_for_price_file_for_station = State()

class GlobalAdminStates(StatesGroup):
    adding_city = State()
    entering_regional_id = State()
    entering_regional_city = State()

class SupplierAdminStates(StatesGroup):
    entering_price = State()

class RoadsideAdminStates(StatesGroup):
    entering_price = State()
    entering_request_id = State()
    choosing_status = State()