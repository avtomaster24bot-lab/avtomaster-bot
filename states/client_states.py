# states/client_states.py
from aiogram.fsm.state import State, StatesGroup

class ClientStates(StatesGroup):
    # ===== Общие =====
    choosing_city = State()
    waiting_for_phone_start = State()

    # ===== СТО =====
    choosing_sto_category = State()
    choosing_sto_subcategories = State()
    entering_sto_description = State()
    confirming_sto_request = State()
    choosing_specific_sto = State()
    waiting_for_phone = State()
    waiting_for_review_text = State()

    # ===== Мойка =====
    choosing_wash = State()
    viewing_wash = State()
    choosing_wash_date = State()
    choosing_wash_slot = State()
    choosing_wash_time = State()
    confirming_wash_booking = State()

    # ===== Эвакуатор =====
    sending_tow_location = State()
    choosing_tow_vehicle_type = State()
    choosing_tow_condition = State()
    entering_tow_comment = State()

    # ===== Автопомощь =====
    sending_roadside_location = State()
    entering_roadside_description = State()
    choosing_roadside_services = State()

    # ===== Запчасти =====
    choosing_part_search_type = State()
    entering_part_name = State()
    entering_parts_car_brand = State()
    entering_parts_car_model = State()
    entering_parts_location = State()
    entering_part_request_name = State()
    entering_part_request_car = State()
    entering_part_request_comment = State()
    waiting_for_part_offers = State()
    entering_price_for_part_offer = State()

    # ===== ИИ-советчик =====
    asking_advice = State()
    paid_diagnostic_payment = State()
    paid_diagnostic_query = State()

    # ===== PriceMaster =====
    entering_price_brand = State()
    entering_price_model = State()
    entering_price_service = State()

    # ===== Сервисная книжка =====
    adding_car_brand = State()
    adding_car_model = State()
    adding_car_year = State()
    adding_car_plate = State()
    choosing_car = State()
    viewing_car = State()
    adding_record_date = State()
    adding_record_mileage = State()
    adding_record_desc = State()
    adding_record_cost = State()

    # ===== Регистрация бизнеса (💼 Для бизнеса) =====
    choosing_partner_type = State()
    entering_partner_name = State()
    entering_partner_address = State()
    entering_partner_phone = State()
    entering_partner_work_hours = State()
    choosing_partner_categories = State()
    entering_partner_boxes = State()
    entering_partner_duration = State()
    choosing_supplier_type = State()
    asking_delivery = State()
    confirming_partner_request = State()
    choosing_urgent_service_type = State()

    # ===== Отзывы и карточки =====
    viewing_station = State()
    viewing_wash = State()
    viewing_tow = State()
    viewing_supplier = State()
    viewing_service = State()
    viewing_reviews = State()

    # ===== Настройки =====
    changing_city = State()

class UrgentServicesStates(StatesGroup):
    sending_location = State()
    entering_description = State()
    entering_price = State()