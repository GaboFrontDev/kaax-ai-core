"""Tests for deterministic ConversationState extraction and routing.

Run with:  pytest tests/test_conversation_state.py -v
"""

from __future__ import annotations

import pytest

from conversation_state import (
    ConversationState,
    choose_specialist_route,
    extract_channel,
    extract_intent,
    extract_product_service,
    extract_volume,
    infer_stage,
    is_greeting,
    is_identity_question,
    missing_fields,
    state_summary_block,
)


# ===========================================================================
# Volume extraction
# ===========================================================================


class TestVolumeExtraction:
    def test_integer_10_gives_menos_de_20(self):
        val, rng = extract_volume("10")
        assert val == 10
        assert rng == "menos de 20"

    def test_integer_10_state_en_desarrollo(self):
        state = ConversationState()
        state.apply_user_turn("Vendo ropa y recibo como 10 mensajes al dia")
        assert state.volumen_mensajes_rango == "menos de 20"
        assert state.volume_fit() == "en_desarrollo"

    def test_200_por_whatsapp_range_and_channel(self):
        state = ConversationState()
        state.apply_user_turn("200 por whatsapp")
        assert state.volumen_mensajes_rango == "100 a 300"
        assert state.canal_principal == "whatsapp"

    def test_explicit_range_menos_de_20(self):
        val, rng = extract_volume("menos de 20")
        assert rng == "menos de 20"
        assert val == 10

    def test_explicit_range_mas_de_300(self):
        val, rng = extract_volume("mas de 300")
        assert rng == "mas de 300"
        assert val == 400

    def test_explicit_range_20_a_100(self):
        val, rng = extract_volume("20 a 100")
        assert rng == "20 a 100"

    def test_explicit_range_100_a_300(self):
        val, rng = extract_volume("100 a 300")
        assert rng == "100 a 300"

    def test_menu_option_1_ignored(self):
        val, rng = extract_volume("1")
        assert val is None and rng is None

    def test_menu_option_2_ignored(self):
        val, rng = extract_volume("2")
        assert val is None and rng is None

    def test_menu_option_3_ignored(self):
        val, rng = extract_volume("3")
        assert val is None and rng is None

    def test_menu_option_4_ignored(self):
        val, rng = extract_volume("4")
        assert val is None and rng is None

    def test_50_gives_20_a_100(self):
        val, rng = extract_volume("50")
        assert rng == "20 a 100"

    def test_300_gives_100_a_300(self):
        val, rng = extract_volume("300")
        assert rng == "100 a 300"

    def test_400_gives_mas_de_300(self):
        val, rng = extract_volume("400 mensajes")
        assert rng == "mas de 300"

    def test_500_in_sentence_gives_mas_de_300(self):
        val, rng = extract_volume("recibo como 500 mensajes al dia")
        assert rng == "mas de 300"

    def test_volume_not_overwritten_once_set(self):
        state = ConversationState()
        state.apply_user_turn("50 mensajes")
        assert state.volumen_mensajes_rango == "20 a 100"
        state.apply_user_turn("300 mensajes")
        # Volume already set — should not overwrite
        assert state.volumen_mensajes_rango == "20 a 100"

    # -- Context-aware extraction (past_menu_phase) --

    def test_bare_3_ignored_during_menu_phase(self):
        """'3' alone is a goal-menu option, not a volume answer."""
        val, rng = extract_volume("3", past_menu_phase=False)
        assert val is None and rng is None

    def test_bare_3_captured_after_menu_phase(self):
        """Once negocio_tipo is set, '3' should parse as volume=3 (en_desarrollo)."""
        val, rng = extract_volume("3", past_menu_phase=True)
        assert val == 3
        assert rng == "menos de 20"

    def test_state_captures_bare_digit_volume_after_negocio_tipo(self):
        """Full apply_user_turn flow: '3' as volume reply after goal selected."""
        state = ConversationState()
        state.apply_user_turn("4")          # goal = marketing
        assert state.negocio_tipo == "marketing"
        state.apply_user_turn("servicios de marketing digital")
        state.apply_user_turn("3")          # volume reply — should now be captured
        assert state.volumen_mensajes_rango == "menos de 20"
        assert state.volumen_mensajes_valor_aprox == 3
        assert state.volume_fit() == "en_desarrollo"

    def test_state_captures_bare_1_as_volume_after_negocio_tipo(self):
        state = ConversationState()
        state.apply_user_turn("ventas")
        state.apply_user_turn("zapatos de piel")
        state.apply_user_turn("1")          # 1 message/day — very low volume
        assert state.volumen_mensajes_rango == "menos de 20"

    def test_guardrail_fires_correctly_with_bare_digit_volume(self):
        """End-to-end: user enters bare '3' as volume → en_desarrollo → qualification."""
        state = ConversationState()
        state.apply_user_turn("4")                           # negocio = marketing
        state.apply_user_turn("servicios de marketing")
        state.apply_user_turn("3")                           # volume = 3
        state.apply_user_turn("whatsapp")
        assert state.volume_fit() == "en_desarrollo"
        route = choose_specialist_route(state)
        assert route == "qualification"
        assert route != "capture"


# ===========================================================================
# Intent detection
# ===========================================================================


class TestIntentDetection:
    def test_precio_gives_alta(self):
        assert extract_intent("quiero saber el precio") == "alta"

    def test_precios_gives_alta(self):
        assert extract_intent("cuales son los precios") == "alta"

    def test_me_interesa_gives_media(self):
        assert extract_intent("me interesa saber mas") == "media"

    def test_demo_gives_alta(self):
        assert extract_intent("quiero agendar una demo") == "alta"

    def test_contratar_gives_alta(self):
        assert extract_intent("quiero contratar el servicio") == "alta"

    def test_planes_gives_alta(self):
        assert extract_intent("vi los planes y quiero el basico") == "alta"

    def test_evaluando_gives_media(self):
        assert extract_intent("estoy evaluando opciones") == "media"

    def test_neutral_gives_none(self):
        assert extract_intent("hola como estas") is None

    def test_state_upgrades_baja_to_media(self):
        state = ConversationState()
        state.apply_user_turn("me interesa")
        assert state.intencion_compra == "media"

    def test_state_upgrades_media_to_alta(self):
        state = ConversationState()
        state.apply_user_turn("me interesa")
        state.apply_user_turn("cuanto cuesta el plan")
        assert state.intencion_compra == "alta"

    def test_intent_never_downgrades(self):
        state = ConversationState()
        state.apply_user_turn("quiero comprar")
        assert state.intencion_compra == "alta"
        state.apply_user_turn("solo preguntando por curiosidad")
        assert state.intencion_compra == "alta"


# ===========================================================================
# Routing guardrails
# ===========================================================================


class TestRoutingGuardrail:
    def _make_state(self, **kwargs) -> ConversationState:
        state = ConversationState()
        for k, v in kwargs.items():
            setattr(state, k, v)
        state.etapa_funnel = infer_stage(state)
        return state

    def test_en_desarrollo_alta_no_demo_gives_qualification_not_capture(self):
        state = self._make_state(
            negocio_tipo="ventas",
            producto_servicio="ropa deportiva",
            volumen_mensajes_rango="menos de 20",
            volumen_mensajes_valor_aprox=10,
            canal_principal="whatsapp",
            intencion_compra="alta",
            requested_demo=False,
            asked_pricing=False,
        )
        route = choose_specialist_route(state)
        assert route != "capture", (
            "en_desarrollo without explicit demo request must never route to capture"
        )
        assert route == "qualification"

    def test_en_desarrollo_requested_demo_allows_capture(self):
        state = self._make_state(
            negocio_tipo="ventas",
            producto_servicio="ropa",
            volumen_mensajes_rango="menos de 20",
            volumen_mensajes_valor_aprox=10,
            canal_principal="whatsapp",
            intencion_compra="alta",
            requested_demo=True,
            asked_pricing=False,
        )
        assert choose_specialist_route(state) == "capture"

    def test_fuerte_alta_intent_gives_capture(self):
        state = self._make_state(
            negocio_tipo="ventas",
            producto_servicio="software crm",
            volumen_mensajes_rango="100 a 300",
            volumen_mensajes_valor_aprox=200,
            canal_principal="whatsapp",
            intencion_compra="alta",
            requested_demo=False,
            asked_pricing=False,
        )
        assert choose_specialist_route(state) == "capture"

    def test_fuerte_media_intent_gives_qualification(self):
        state = self._make_state(
            negocio_tipo="ventas",
            producto_servicio="software crm",
            volumen_mensajes_rango="20 a 100",
            volumen_mensajes_valor_aprox=50,
            canal_principal="instagram",
            intencion_compra="media",
            requested_demo=False,
            asked_pricing=False,
        )
        assert choose_specialist_route(state) == "qualification"

    def test_asked_pricing_gives_knowledge(self):
        state = self._make_state(
            negocio_tipo="ventas",
            producto_servicio="ropa",
            volumen_mensajes_rango="menos de 20",
            volumen_mensajes_valor_aprox=10,
            canal_principal="whatsapp",
            intencion_compra="alta",
            asked_pricing=True,
        )
        assert choose_specialist_route(state) == "knowledge"

    def test_incomplete_state_no_negocio_gives_discovery(self):
        state = ConversationState()
        assert choose_specialist_route(state) == "discovery"

    def test_partial_info_gives_discovery(self):
        state = self._make_state(negocio_tipo="ventas")
        # Missing producto_servicio, volumen, canal → diagnostico → discovery
        assert choose_specialist_route(state) == "discovery"

    def test_en_desarrollo_media_intent_no_demo_gives_qualification(self):
        state = self._make_state(
            negocio_tipo="atencion",
            producto_servicio="restaurante",
            volumen_mensajes_rango="menos de 20",
            volumen_mensajes_valor_aprox=5,
            canal_principal="whatsapp",
            intencion_compra="media",
            requested_demo=False,
            asked_pricing=False,
        )
        route = choose_specialist_route(state)
        assert route != "capture"
        assert route == "qualification"


# ===========================================================================
# Greeting and identity detection
# ===========================================================================


class TestIdentityGreetingDetection:
    def test_hola_is_greeting(self):
        assert is_greeting("hola") is True

    def test_buenas_tardes_is_greeting(self):
        assert is_greeting("Buenas tardes") is True

    def test_hey_is_greeting(self):
        assert is_greeting("hey") is True

    def test_hello_is_greeting(self):
        assert is_greeting("Hello") is True

    def test_ai_trigger_is_greeting(self):
        assert is_greeting("AI") is True

    def test_hola_ai_is_greeting(self):
        assert is_greeting("hola AI") is True

    def test_pricing_question_not_greeting(self):
        assert is_greeting("cuanto cuesta el plan") is False

    def test_long_question_not_greeting(self):
        assert is_greeting("quiero saber mas sobre sus servicios") is False

    def test_quien_eres_is_identity(self):
        assert is_identity_question("quien eres") is True

    def test_quien_eres_with_accent_is_identity(self):
        assert is_identity_question("quién eres") is True

    def test_que_eres_is_identity(self):
        assert is_identity_question("qué eres exactamente") is True

    def test_eres_bot_is_identity(self):
        assert is_identity_question("eres un bot?") is True

    def test_eres_ia_is_identity(self):
        assert is_identity_question("eres una ia") is True

    def test_hablas_con_humano_is_identity(self):
        assert is_identity_question("hablas con un humano") is True

    def test_normal_question_not_identity(self):
        assert is_identity_question("cuantos mensajes recibo") is False

    def test_pricing_not_identity(self):
        assert is_identity_question("cuanto cuesta el plan basico") is False


# ===========================================================================
# Channel extraction
# ===========================================================================


class TestChannelExtraction:
    def test_whatsapp(self):
        assert extract_channel("llegan por whatsapp") == "whatsapp"

    def test_wsp_abbreviation(self):
        assert extract_channel("por wsp generalmente") == "whatsapp"

    def test_instagram(self):
        assert extract_channel("uso instagram principalmente") == "instagram"

    def test_ig_abbreviation(self):
        assert extract_channel("mis clientes me escriben por ig") == "instagram"

    def test_facebook(self):
        assert extract_channel("tengo un facebook activo") == "facebook"

    def test_web(self):
        assert extract_channel("en mi pagina web") == "web"

    def test_no_channel(self):
        assert extract_channel("vendo zapatos de piel") is None


# ===========================================================================
# State summary block
# ===========================================================================


class TestStateSummaryBlock:
    def test_no_links_when_en_desarrollo_no_demo_no_pricing(self):
        state = ConversationState()
        state.volumen_mensajes_rango = "menos de 20"
        state.intencion_compra = "alta"
        state.requested_demo = False
        state.asked_pricing = False
        block = state_summary_block(state, "https://demo.example.com", "https://pricing.example.com")
        assert "demo.example.com" not in block
        assert "pricing.example.com" not in block

    def test_demo_link_injected_when_requested_demo(self):
        state = ConversationState()
        state.requested_demo = True
        block = state_summary_block(state, "https://demo.example.com", "https://pricing.example.com")
        assert "https://demo.example.com" in block

    def test_pricing_link_injected_when_asked_pricing(self):
        state = ConversationState()
        state.asked_pricing = True
        block = state_summary_block(state, "https://demo.example.com", "https://pricing.example.com")
        assert "https://pricing.example.com" in block

    def test_demo_link_injected_when_fuerte_and_alta_intent(self):
        state = ConversationState()
        state.volumen_mensajes_rango = "100 a 300"
        state.intencion_compra = "alta"
        block = state_summary_block(state, "https://demo.example.com", "https://pricing.example.com")
        assert "https://demo.example.com" in block

    def test_block_contains_state_fields(self):
        state = ConversationState()
        state.negocio_tipo = "ventas"
        state.producto_servicio = "software"
        state.canal_principal = "whatsapp"
        block = state_summary_block(state, "https://demo.example.com", "https://pricing.example.com")
        assert "ventas" in block
        assert "software" in block
        assert "whatsapp" in block


# ===========================================================================
# Missing fields + stage inference
# ===========================================================================


class TestMissingFieldsAndStage:
    def test_empty_state_missing_all(self):
        state = ConversationState()
        assert set(missing_fields(state)) == {
            "producto_servicio",
            "volumen_mensajes_rango",
            "canal_principal",
        }

    def test_all_fields_present_no_missing(self):
        state = ConversationState()
        state.producto_servicio = "zapatos"
        state.volumen_mensajes_rango = "20 a 100"
        state.canal_principal = "whatsapp"
        assert missing_fields(state) == []

    def test_no_negocio_tipo_gives_primer_contacto(self):
        state = ConversationState()
        assert infer_stage(state) == "primer_contacto"

    def test_missing_fields_gives_diagnostico(self):
        state = ConversationState()
        state.negocio_tipo = "ventas"
        assert infer_stage(state) == "diagnostico"

    def test_full_state_media_intent_gives_calificacion(self):
        state = ConversationState()
        state.negocio_tipo = "ventas"
        state.producto_servicio = "ropa"
        state.volumen_mensajes_rango = "20 a 100"
        state.canal_principal = "instagram"
        state.intencion_compra = "media"
        assert infer_stage(state) == "calificacion"

    def test_full_state_fuerte_alta_gives_cierre(self):
        state = ConversationState()
        state.negocio_tipo = "ventas"
        state.producto_servicio = "ropa"
        state.volumen_mensajes_rango = "100 a 300"
        state.canal_principal = "whatsapp"
        state.intencion_compra = "alta"
        assert infer_stage(state) == "cierre"

    def test_en_desarrollo_alta_no_demo_gives_nutricion(self):
        state = ConversationState()
        state.negocio_tipo = "ventas"
        state.producto_servicio = "artesanias"
        state.volumen_mensajes_rango = "menos de 20"
        state.canal_principal = "instagram"
        state.intencion_compra = "alta"
        state.requested_demo = False
        assert infer_stage(state) == "nutricion"


# ===========================================================================
# End-to-end turn simulation
# ===========================================================================


class TestEndToEndTurnSimulation:
    def test_full_discovery_flow(self):
        state = ConversationState()

        state.apply_user_turn("hola")
        assert state.etapa_funnel == "primer_contacto"

        state.apply_user_turn("1")  # ventas
        assert state.negocio_tipo == "ventas"

        state.apply_user_turn("Vendo calzado deportivo")
        assert state.producto_servicio is not None
        assert "calzado" in state.producto_servicio.lower()

        state.apply_user_turn("recibo como 50 mensajes al dia por whatsapp")
        assert state.volumen_mensajes_rango == "20 a 100"
        assert state.canal_principal == "whatsapp"
        assert state.etapa_funnel == "calificacion"

    def test_demo_request_sets_flag(self):
        state = ConversationState()
        state.apply_user_turn("quiero agendar una demo")
        assert state.requested_demo is True
        assert state.intencion_compra == "alta"

    def test_email_extracted(self):
        state = ConversationState()
        state.apply_user_turn("mi correo es juan@empresa.com")
        assert state.contact_email == "juan@empresa.com"

    def test_phone_extracted(self):
        state = ConversationState()
        state.apply_user_turn("mi numero es +52 55 1234 5678")
        assert state.contact_phone is not None
        assert len(state.contact_phone) >= 8


# ===========================================================================
# en_desarrollo messaging guardrail (volume coherence)
# ===========================================================================


class TestEnDesarrolloMessagingGuardrail:
    """Validate that prospects with <20 msgs/day are never routed to capture
    and always end up in a route that produces growth-oriented messaging."""

    def _build_ropa_whatsapp_state(self, volume: int) -> ConversationState:
        state = ConversationState()
        state.apply_user_turn("ventas")
        state.apply_user_turn("Vendo ropa")          # 2 words → captured as producto_servicio
        state.apply_user_turn(f"{volume} mensajes")  # bare int with context → captured as volume
        state.apply_user_turn("whatsapp")
        return state

    def test_2_mensajes_routes_to_qualification_not_capture(self):
        state = self._build_ropa_whatsapp_state(2)
        assert state.volume_fit() == "en_desarrollo"
        assert state.volumen_mensajes_rango == "menos de 20"
        route = choose_specialist_route(state)
        assert route == "qualification"
        assert route != "capture"

    def test_5_mensajes_routes_to_qualification(self):
        state = self._build_ropa_whatsapp_state(5)
        assert state.volume_fit() == "en_desarrollo"
        route = choose_specialist_route(state)
        assert route == "qualification"

    def test_15_mensajes_routes_to_qualification(self):
        state = self._build_ropa_whatsapp_state(15)
        assert state.volume_fit() == "en_desarrollo"
        route = choose_specialist_route(state)
        assert route == "qualification"

    def test_summary_block_has_no_demo_link_for_en_desarrollo(self):
        state = self._build_ropa_whatsapp_state(2)
        block = state_summary_block(state, "https://demo.test", "https://pricing.test")
        # Demo link must NOT appear for en_desarrollo without explicit request
        assert "https://demo.test" not in block

    def test_en_desarrollo_with_explicit_demo_request_allows_capture(self):
        """User says demo explicitly — override is allowed."""
        state = self._build_ropa_whatsapp_state(2)
        state.apply_user_turn("quiero agendar una demo")
        assert state.requested_demo is True
        route = choose_specialist_route(state)
        assert route == "capture"

    def test_en_desarrollo_with_pricing_request_routes_to_knowledge(self):
        state = self._build_ropa_whatsapp_state(2)
        state.apply_user_turn("cuanto cuesta el plan")
        assert state.asked_pricing is True
        route = choose_specialist_route(state)
        assert route == "knowledge"

    def test_state_summary_shows_en_desarrollo_label(self):
        state = self._build_ropa_whatsapp_state(2)
        block = state_summary_block(state, "https://demo.test", "https://pricing.test")
        assert "en_desarrollo" in block

    def test_20_mensajes_is_fuerte(self):
        """Boundary: exactly 20 messages → fuerte, eligible for capture."""
        state = self._build_ropa_whatsapp_state(20)
        assert state.volume_fit() == "fuerte"

    def test_19_mensajes_is_en_desarrollo(self):
        state = self._build_ropa_whatsapp_state(19)
        assert state.volume_fit() == "en_desarrollo"
