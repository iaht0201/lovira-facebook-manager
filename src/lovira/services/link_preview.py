"""
Lovira Workspace 2.0 — Shopee & Product Link Preview Service
Trích xuất thông tin xem trước link Shopee và e-commerce:
- Tự động dò và theo dõi redirect (hỗ trợ s.shopee.vn, shope.ee, shopee.vn)
- Trích xuất OpenGraph tags: Tiêu đề sản phẩm, ảnh thumbnail, giá, mô tả
- Tải và lưu trữ bộ nhớ đệm ảnh (local cache) an toàn cho PySide6 QPixmap
- Luồng bất đồng bộ (AsyncLinkPreviewWorker) không làm đơ giao diện người dùng
"""

import os
import re
import hashlib
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)

# Thư mục cache ảnh xem trước
CACHE_DIR = Path.home() / ".lovira" / "cache" / "link_previews"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class LinkPreviewService:
    """Dịch vụ trích xuất và xem trước liên kết sản phẩm Shopee & Web."""

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    _instance: Optional["LinkPreviewService"] = None

    @classmethod
    def get_instance(cls) -> "LinkPreviewService":
        if cls._instance is None:
            cls._instance = LinkPreviewService()
        return cls._instance

    @staticmethod
    def extract_urls(text: str) -> List[str]:
        """Trích xuất tất cả các đường dẫn URL từ văn bản."""
        if not text:
            return []
        pattern = r"https?://[^\s<>\"\'\)]+"
        return re.findall(pattern, text)

    @staticmethod
    def is_shopee_url(url: str) -> bool:
        """Kiểm tra xem URL có thuộc hệ sinh thái Shopee hay không."""
        clean_url = url.lower()
        return any(d in clean_url for d in ("shopee.vn", "s.shopee.vn", "shope.ee", "shp.ee"))

    def fetch_preview(self, url: str, timeout: float = 6.0) -> Dict[str, Any]:
        """
        Lấy thông tin xem trước từ URL (theo dõi redirect, parse OpenGraph và tải ảnh cache).
        Trả về dict: {url, final_url, title, image_url, local_image_path, price, description, platform}
        """
        url = url.strip()
        result: Dict[str, Any] = {
            "url": url,
            "final_url": url,
            "title": "",
            "image_url": "",
            "local_image_path": "",
            "price": "",
            "description": "",
            "platform": "shopee" if self.is_shopee_url(url) else "web",
            "success": False,
        }

        try:
            resp = requests.get(
                url,
                headers=self.DEFAULT_HEADERS,
                timeout=timeout,
                allow_redirects=True,
            )
            result["final_url"] = resp.url
            if "shopee" in resp.url.lower():
                result["platform"] = "shopee"

            if resp.status_code != 200:
                logger.debug(f"Không thể tải link {url}: status {resp.status_code}")
                return result

            soup = BeautifulSoup(resp.text, "html.parser")

            # 1. Trích xuất Tiêu đề
            og_title = soup.find("meta", property="og:title")
            twitter_title = soup.find("meta", attrs={"name": "twitter:title"})
            page_title = soup.find("title")

            raw_title = ""
            if og_title and og_title.get("content"):
                raw_title = og_title["content"].strip()
            elif twitter_title and twitter_title.get("content"):
                raw_title = twitter_title["content"].strip()
            elif page_title and page_title.text:
                raw_title = page_title.text.strip()

            # Dọn dẹp tiêu đề Shopee
            clean_title = raw_title
            for suffix in ["| Shopee Việt Nam", "- Shopee", "| Shopee"]:
                if suffix in clean_title:
                    clean_title = clean_title.replace(suffix, "").strip()
            if clean_title.lower().startswith("mua "):
                clean_title = clean_title[4:].strip()

            result["title"] = clean_title or raw_title

            # 2. Trích xuất Ảnh Thumbnail
            og_image = soup.find("meta", property="og:image")
            twitter_image = soup.find("meta", attrs={"name": "twitter:image"})

            img_url = ""
            if og_image and og_image.get("content"):
                img_url = og_image["content"].strip()
            elif twitter_image and twitter_image.get("content"):
                img_url = twitter_image["content"].strip()

            result["image_url"] = img_url

            # 3. Trích xuất Mô tả & Giá
            og_desc = soup.find("meta", property="og:description")
            # 3. Trích xuất giá sản phẩm (từ meta tags, description hoặc title)
            og_price = soup.find("meta", property="product:price:amount") or soup.find("meta", property="og:price:amount")
            if og_price and og_price.get("content"):
                amt_str = og_price["content"].strip()
                try:
                    amt_num = int(float(amt_str))
                    result["price"] = f"{amt_num:,}đ".replace(",", ".")
                except (ValueError, TypeError):
                    result["price"] = f"{amt_str}đ"

            if og_desc and og_desc.get("content"):
                result["description"] = og_desc["content"].strip()

                # Dò giá sản phẩm trong description nếu chưa có
                if not result["price"]:
                    price_match = re.search(r"(?:₫|đ|\$)\s?[\d.,]+|[\d.,]+\s?(?:₫|đ|VND|k)", result["description"], re.IGNORECASE)
                    if price_match:
                        result["price"] = price_match.group(0).strip()

            if not result["price"] and result["title"]:
                price_match = re.search(r"(?:₫|đ)\s?[\d.,]+|[\d.,]+\s?(?:₫|đ|k)", result["title"], re.IGNORECASE)
                if price_match:
                    result["price"] = price_match.group(0).strip()

            # 4. Tải ảnh thumbnail về local cache để PySide6 hiển thị tức thì
            if img_url:
                local_path = self._cache_image(img_url)
                result["local_image_path"] = local_path

            result["success"] = bool(result["title"] or result["image_url"])

        except Exception as e:
            logger.debug(f"Lỗi phân tích preview link {url}: {e}")
            result["error"] = str(e)

        return result

    def _cache_image(self, img_url: str) -> str:
        """Tải ảnh và lưu vào thư mục cache, trả về đường dẫn file cục bộ."""
        try:
            url_hash = hashlib.md5(img_url.encode("utf-8")).hexdigest()
            ext = ".jpg"
            if ".png" in img_url.lower():
                ext = ".png"
            elif ".webp" in img_url.lower():
                ext = ".webp"

            target_path = CACHE_DIR / f"{url_hash}{ext}"
            if target_path.exists() and target_path.stat().st_size > 0:
                return str(target_path)

            img_resp = requests.get(img_url, headers=self.DEFAULT_HEADERS, timeout=5.0)
            if img_resp.status_code == 200 and len(img_resp.content) > 0:
                target_path.write_bytes(img_resp.content)
                return str(target_path)
        except Exception as e:
            logger.debug(f"Lỗi tải cache ảnh {img_url}: {e}")
        return ""


class AsyncLinkPreviewWorker(QThread):
    """Worker chạy ngầm để lấy thông tin xem trước link mà không đơ UI."""

    preview_ready = Signal(dict)
    preview_failed = Signal(str, str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self) -> None:
        service = LinkPreviewService.get_instance()
        try:
            data = service.fetch_preview(self.url)
            if data.get("success"):
                self.preview_ready.emit(data)
            else:
                self.preview_failed.emit(self.url, data.get("error", "Không thể lấy thông tin sản phẩm"))
        except Exception as e:
            self.preview_failed.emit(self.url, str(e))
