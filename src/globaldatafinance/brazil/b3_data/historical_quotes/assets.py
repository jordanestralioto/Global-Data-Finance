"""Asset class validation and TPMERC code mapping."""

from typing import ClassVar

from .errors import EmptyAssetListError, InvalidAssetsName


class AvailableAssetsServiceB3:
    """Domain service for validating and managing available asset classes.

    TPMERC Codes Reference:
    - 010: CASH (Vista)
    - 020: FRACTIONARY (Fracionário)
    - 030: TERM (Termo)
    - 050: FORWARD WITH GAIN (Forward c/ prêmio)
    - 060: FORWARD WITH MOVEMENT (Forward c/ movimentação)
    - 070: CALL OPTIONS (Opções de Compra)
    - 080: PUT OPTIONS (Opções de Venda)
    - 012: CALL EXERCISE (Exercício de Compra)
    - 013: PUT EXERCISE (Exercício de Venda)
    - 017: AUCTION (Leilão)
    - 021: BLOCK LOT (Lote em Bloco)
    """

    _AVAILABLE_ASSETS_BY_CLASS: ClassVar[dict[str, list[str]]] = {
        'ações': ['010', '020'],
        'etf': ['010', '020'],
        'opções': ['070', '080'],
        'termo': ['030'],
        'exercicio_opcoes': ['012', '013'],
        'forward': ['050', '060'],
        'leilao': ['017'],
        'lote_bloco': ['021'],
        'todos': [],
    }

    @classmethod
    def get_available_assets(cls) -> list[str]:
        """Return the list of available asset class names."""
        return list(cls._AVAILABLE_ASSETS_BY_CLASS.keys())

    @classmethod
    def validate_and_create_asset_set(cls, assets_list: list[str]) -> set[str]:
        """Validate the provided list of asset classes and return a set."""
        if not isinstance(assets_list, list) or not assets_list:
            raise EmptyAssetListError()

        if not all(isinstance(asset, str) for asset in assets_list):
            raise InvalidAssetsName(
                assets_list=assets_list,
                list_available_assets=cls.get_available_assets(),
            )

        assets_list = [asset.lower() for asset in assets_list]

        if not all(
            asset in cls._AVAILABLE_ASSETS_BY_CLASS for asset in assets_list
        ):
            raise InvalidAssetsName(
                assets_list=assets_list,
                list_available_assets=cls.get_available_assets(),
            )

        return set(assets_list)

    @classmethod
    def get_tpmerc_codes_for_assets(cls, asset_set: set[str]) -> set[str]:
        """Convert validated asset classes to their TPMERC codes."""
        return {
            code
            for asset_class in asset_set
            if asset_class != 'todos'
            for code in cls._AVAILABLE_ASSETS_BY_CLASS[asset_class]
        }
