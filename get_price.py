import json
from typing import List, Dict, Optional, Union
import requests
from loguru import logger
from get_token import get_token
from get_price_with_wb_wallet import calc_price_with_wb_wallet
import sys


HEADERS = {
    "accept": "*/*",
    "accept-language": "ru-RU,ru;q=0.9",
    "priority": "u=1, i",
    "referer": "https://www.wildberries.ru/catalog/0/search.aspx?search=%D0%BD%D0%BE%D0%B2%D0%BE%D0%B3%D0%BE%D0%B4%D0%BD%D0%B8%D0%B5%20%D1%83%D0%BA%D1%80%D0%B0%D1%88%D0%B5%D0%BD%D0%B8%D1%8F",
    "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest",
    "x-spa-version": "13.15.1",
    "x-userid": "0",
}
TOKEN = '1.1000.fec0a7a9119347a68cfed0a1a42821f2.MTV8OTQuMTAzLjk0LjEzMXxNb3ppbGxhLzUuMCAoV2luZG93cyBOVCAxMC4wOyBXaW42NDsgeDY0KSBBcHBsZVdlYktpdC81MzcuMzYgKEtIVE1MLCBsaWtlIEdlY2tvKSBDaHJvbWUvMTQyLjAuMC4wIFNhZmFyaS81MzcuMzZ8MTc3MDA1MzQyN3xyZXVzYWJsZXwyfGV5Sm9ZWE5vSWpvaUluMD18MHwzfDE3Njk0NDg2Mjd8MQ==.MEQCIG/TuBJiikFX6mB9jQGWLM44SO0lDlGvmkpqVLjI5jqiAiAJg05KnK84UhP80ogghp+AFPPfuVtBuUBlTyMtegB+lw=='

class WbPrice:
    SEARCH_URL = "https://www.wildberries.ru/__internal/u-card/cards/v4/detail"
    DEFAULT_PARAMS = {
        "ab_testing": ["false", "false"],
        "appType": "1",
        "curr": "rub",
        "dest": "12358536",
        "hide_dtype": "11",
        "hide_vflags": "4294967296",
        "lang": "ru",
        "spp": "30",
    }

    def __init__(self, goods: List, token: Optional[str] = None):
        self.goods = goods
        self.token = TOKEN or get_token()

    def _update_token(self) -> None:
        logger.info("Обновляем токен")
        self.token = get_token()
        logger.info(f"Токен обновлен: {self.token}")

    def _make_request(self, sku: str, retries: int = 2) -> Optional[Dict]:
        params = self.DEFAULT_PARAMS.copy()
        params["nm"] = sku

        for attempt in range(1, retries + 1):
            logger.info(f"Попытка {attempt} для id {sku}")
            try:
                response = requests.get(
                    self.SEARCH_URL,
                    params=params,
                    cookies={"x_wbaas_token": self.token},
                    headers=HEADERS,
                )

                if response.status_code == 498:
                    logger.warning("Код 498. Обновляем токен.")
                    self._update_token()
                    continue

                if response.status_code != 200:
                    logger.warning(f"Ошибка {response.status_code} при запросе SKU {sku}")
                    return None

                return response.json()

            except requests.RequestException as e:
                logger.error(f"Ошибка запроса: {e}")

        logger.warning(f"Не удалось получить данные для SKU {sku} после {retries} попыток")
        return None

    def _extract_sku_info(self, data: Dict, sku: Union[str, int]) -> Optional[Dict]:
        try:
            products = data.get("products", [])
            if not products:
                logger.warning("Нет продуктов в ответе JSON")
                return None

            sku = int(sku)
            for product in products:
                if product.get("id") == sku:
                    sizes = product.get("sizes", [{}])[0]
                    price_info = sizes.get("price", {})

                    return {
                        "price": calc_price_with_wb_wallet(price_info.get("product", 0) / 100),
                        "basic_price": price_info.get("basic", 0) / 100,
                        "name": product.get("name"),
                        "rating": product.get("reviewRating"),
                        "feedbacks": product.get("feedbacks"),
                    }
        except (ValueError, IndexError, KeyError) as e:
            logger.error(f"Ошибка при обработке id {sku}: {e}")

        return None

    def parse_prices(self) -> List[Dict]:
        results = []

        for good in self.goods:
            sku = good
            if not sku:
                logger.warning("Пропущен товар без SKU")
                results.append({"sku": None, "price": None, "basic_price": None, "name": None, "rating": None, "feedbacks": None})
                continue

            data = self._make_request(sku)
            if not data:
                results.append({"sku": sku, "price": None, "basic_price": None, "name": None, "rating": None, "feedbacks": None})
                continue

            sku_info = self._extract_sku_info(data, sku)
            if not sku_info:
                results.append({"sku": sku, "price": None, "basic_price": None, "name": None, "rating": None, "feedbacks": None})
                continue

            results.append({"sku": sku, **sku_info})

        return results

def add_sku_from_terminal():
    if len(sys.argv) < 2:
        logger.error("Не указан SKU. Используйте: python get_price.py sku=<значение>")
        return

    arg = sys.argv[1]
    if not arg.startswith("sku="):
        logger.error("Неверный формат аргумента. Используйте: python get_price.py sku=<значение>")
        return

    try:
        sku = int(arg.split("=", 1)[1])
        wb_price = WbPrice(goods=[sku])
        results = wb_price.parse_prices()
        logger.success(results)
    except ValueError:
        logger.error("SKU должен быть числом.")

if __name__ == "__main__":
    
    if len(sys.argv) > 1:
        add_sku_from_terminal()
    else:
        input_list = [294493176]
        wb_price = WbPrice(goods=input_list)
        results = wb_price.parse_prices()
        logger.success(results)
