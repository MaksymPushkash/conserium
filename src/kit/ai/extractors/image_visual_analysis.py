from __future__ import annotations

from statistics import fmean
from typing import Any, TypedDict


class _OCRWordBox(TypedDict):
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int


class _DiagramBox(TypedDict):
    id: str
    x: int
    y: int
    width: int
    height: int
    text: str


class _DiagramConnector(TypedDict):
    id: str
    orientation: str
    x1: int
    y1: int
    x2: int
    y2: int
    direction: str
    from_box_id: str | None
    to_box_id: str | None


class _DiagramRelationship(TypedDict):
    from_box_id: str
    to_box_id: str
    relation: str
    confidence: float


class ImageVisualAnalyzer:
    def analyze(self, pytesseract: Any, img: Any, *, language: str) -> dict[str, object]:
        width, height = img.size
        boxes = self._extract_word_boxes(pytesseract, img, language=language)
        non_empty_boxes = [box for box in boxes if box["text"]]
        confidences = [box["confidence"] for box in non_empty_boxes if box["confidence"] >= 0]
        average_confidence = round(fmean(confidences), 3) if confidences else 0.0

        line_count = self._estimate_line_count(non_empty_boxes)
        block_count = self._estimate_block_count(non_empty_boxes)
        edge_density = round(self._edge_density(img), 4)
        text_coverage = round(
            sum(box["width"] * box["height"] for box in non_empty_boxes) / max(width * height, 1),
            4,
        )
        layout_type = self._classify_layout(
            edge_density=edge_density,
            text_coverage=text_coverage,
            word_count=len(non_empty_boxes),
            line_count=line_count,
        )
        diagram_boxes = self._detect_diagram_boxes(img, non_empty_boxes)
        diagram_connectors = self._detect_diagram_connectors(img, diagram_boxes)
        diagram_relationships = self._infer_diagram_relationships(diagram_connectors)
        diagram_type = self._classify_diagram_type(layout_type, diagram_boxes, diagram_connectors)

        return {
            "layout_type": layout_type,
            "diagram_type": diagram_type,
            "width": width,
            "height": height,
            "orientation": "landscape" if width >= height else "portrait",
            "ocr_word_count": len(non_empty_boxes),
            "ocr_line_count": line_count,
            "text_block_count": block_count,
            "average_ocr_confidence": average_confidence,
            "text_coverage": text_coverage,
            "edge_density": edge_density,
            "diagram_boxes": diagram_boxes,
            "diagram_connectors": diagram_connectors,
            "diagram_relationships": diagram_relationships,
        }

    def _extract_word_boxes(self, pytesseract: Any, img: Any, *, language: str) -> list[_OCRWordBox]:
        if not hasattr(pytesseract, "image_to_data") or not hasattr(pytesseract, "Output"):
            return []
        data = pytesseract.image_to_data(img, lang=language, output_type=pytesseract.Output.DICT)
        words: list[_OCRWordBox] = []
        total = len(data.get("text", []))
        for index in range(total):
            text = str(data["text"][index]).strip()
            confidence = float(data["conf"][index]) if data["conf"][index] != "-1" else -1.0
            words.append(
                {
                    "text": text,
                    "confidence": confidence,
                    "left": int(data["left"][index]),
                    "top": int(data["top"][index]),
                    "width": int(data["width"][index]),
                    "height": int(data["height"][index]),
                }
            )
        return words

    def _estimate_line_count(self, boxes: list[_OCRWordBox]) -> int:
        if not boxes:
            return 0
        sorted_boxes = sorted(boxes, key=lambda box: box["top"])
        lines = 0
        last_top: int | None = None
        vertical_threshold = 18
        for box in sorted_boxes:
            if last_top is None or abs(box["top"] - last_top) > vertical_threshold:
                lines += 1
                last_top = box["top"]
        return lines

    def _estimate_block_count(self, boxes: list[_OCRWordBox]) -> int:
        if not boxes:
            return 0
        sorted_boxes = sorted(boxes, key=lambda box: (box["top"], box["left"]))
        blocks = 1
        last_bottom = sorted_boxes[0]["top"] + sorted_boxes[0]["height"]
        for box in sorted_boxes[1:]:
            current_top = box["top"]
            if current_top - last_bottom > 40:
                blocks += 1
            last_bottom = max(last_bottom, box["top"] + box["height"])
        return blocks

    def _classify_layout(
        self,
        *,
        edge_density: float,
        text_coverage: float,
        word_count: int,
        line_count: int,
    ) -> str:
        if word_count >= 25 and line_count >= 5 and text_coverage >= 0.08:
            return "document"
        if word_count >= 10 and edge_density >= 0.09:
            return "screenshot"
        if word_count <= 20 and edge_density >= 0.12:
            return "diagram"
        return "image"

    def _classify_diagram_type(
        self,
        layout_type: str,
        boxes: list[_DiagramBox],
        connectors: list[_DiagramConnector],
    ) -> str:
        if len(boxes) >= 2 and connectors:
            return "flowchart"
        if boxes:
            return "boxed_diagram"
        if connectors:
            return "line_diagram"
        return layout_type

    def _detect_diagram_boxes(self, img: Any, word_boxes: list[_OCRWordBox]) -> list[_DiagramBox]:
        components = self._connected_dark_components(img)
        candidates: list[tuple[int, int, int, int]] = []
        image_width, image_height = img.size
        min_area = max(600, int(image_width * image_height * 0.002))

        for x1, y1, x2, y2, pixel_count in components:
            width = x2 - x1 + 1
            height = y2 - y1 + 1
            area = width * height
            if area < min_area or width < 35 or height < 20:
                continue
            fill_ratio = pixel_count / max(area, 1)
            border_ratio = self._component_border_ratio(img, x1, y1, x2, y2)
            if fill_ratio <= 0.35 and border_ratio >= 0.25:
                candidates.append((x1, y1, x2, y2))

        merged = self._merge_overlapping_rectangles(candidates)
        boxes: list[_DiagramBox] = []
        for index, (x1, y1, x2, y2) in enumerate(merged[:20], start=1):
            text = self._text_inside_rectangle(word_boxes, x1, y1, x2, y2)
            boxes.append(
                {
                    "id": f"box_{index}",
                    "x": x1,
                    "y": y1,
                    "width": x2 - x1 + 1,
                    "height": y2 - y1 + 1,
                    "text": text,
                }
            )
        return boxes

    def _detect_diagram_connectors(self, img: Any, boxes: list[_DiagramBox]) -> list[_DiagramConnector]:
        dark = self._dark_pixel_grid(img)
        if not dark:
            return []
        height = len(dark)
        width = len(dark[0]) if height else 0
        segments: list[tuple[str, int, int, int, int]] = []
        min_length = max(30, min(width, height) // 12)

        for y, row in enumerate(dark):
            start: int | None = None
            for x, value in enumerate([*row, False]):
                if value and start is None:
                    start = x
                if (not value or x == width) and start is not None:
                    end = x - 1
                    if end - start + 1 >= min_length:
                        segments.append(("horizontal", start, y, end, y))
                    start = None

        for x in range(width):
            start = None
            for y in range(height + 1):
                value = dark[y][x] if y < height else False
                if value and start is None:
                    start = y
                if (not value or y == height) and start is not None:
                    end = y - 1
                    if end - start + 1 >= min_length:
                        segments.append(("vertical", x, start, x, end))
                    start = None

        connectors: list[_DiagramConnector] = []
        for index, (orientation, x1, y1, x2, y2) in enumerate(self._dedupe_segments(segments)[:30], start=1):
            from_box_id, to_box_id = self._nearest_endpoint_boxes(boxes, x1, y1, x2, y2)
            connectors.append(
                {
                    "id": f"connector_{index}",
                    "orientation": orientation,
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "direction": self._infer_connector_direction(orientation, x1, y1, x2, y2, from_box_id, to_box_id),
                    "from_box_id": from_box_id,
                    "to_box_id": to_box_id,
                }
            )
        return connectors

    def _infer_diagram_relationships(
        self,
        connectors: list[_DiagramConnector],
    ) -> list[_DiagramRelationship]:
        relationships: list[_DiagramRelationship] = []
        seen: set[tuple[str, str]] = set()
        for connector in connectors:
            from_id = connector["from_box_id"]
            to_id = connector["to_box_id"]
            if from_id is None or to_id is None or from_id == to_id:
                continue
            key = (from_id, to_id)
            if key in seen:
                continue
            seen.add(key)
            relationships.append(
                {
                    "from_box_id": from_id,
                    "to_box_id": to_id,
                    "relation": "connects_to",
                    "confidence": 0.7,
                }
            )
        return relationships

    def _connected_dark_components(self, img: Any) -> list[tuple[int, int, int, int, int]]:
        dark = self._dark_pixel_grid(img)
        if not dark:
            return []
        height = len(dark)
        width = len(dark[0])
        visited = [[False for _ in range(width)] for _ in range(height)]
        components: list[tuple[int, int, int, int, int]] = []

        for y in range(height):
            for x in range(width):
                if visited[y][x] or not dark[y][x]:
                    continue
                stack = [(x, y)]
                visited[y][x] = True
                min_x = max_x = x
                min_y = max_y = y
                count = 0
                while stack:
                    current_x, current_y = stack.pop()
                    count += 1
                    min_x = min(min_x, current_x)
                    max_x = max(max_x, current_x)
                    min_y = min(min_y, current_y)
                    max_y = max(max_y, current_y)
                    for next_x, next_y in (
                        (current_x - 1, current_y),
                        (current_x + 1, current_y),
                        (current_x, current_y - 1),
                        (current_x, current_y + 1),
                    ):
                        if 0 <= next_x < width and 0 <= next_y < height and not visited[next_y][next_x] and dark[next_y][next_x]:
                            visited[next_y][next_x] = True
                            stack.append((next_x, next_y))
                components.append((min_x, min_y, max_x, max_y, count))
        return components

    def _dark_pixel_grid(self, img: Any) -> list[list[bool]]:
        try:
            gray = img.convert("L")
            width, height = gray.size
            max_dimension = max(width, height)
            if max_dimension > 900:
                scale = 900 / max_dimension
                new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
                gray = gray.resize(new_size)
            pixels = gray.load()
            return [[int(pixels[x, y]) < 96 for x in range(gray.size[0])] for y in range(gray.size[1])]
        except Exception:
            return []

    def _component_border_ratio(self, img: Any, x1: int, y1: int, x2: int, y2: int) -> float:
        dark = self._dark_pixel_grid(img)
        if not dark:
            return 0.0
        width = len(dark[0])
        height = len(dark)
        x1 = max(0, min(x1, width - 1))
        x2 = max(0, min(x2, width - 1))
        y1 = max(0, min(y1, height - 1))
        y2 = max(0, min(y2, height - 1))
        border_pixels = 0
        dark_border_pixels = 0
        for x in range(x1, x2 + 1):
            for y in (y1, y2):
                border_pixels += 1
                dark_border_pixels += int(dark[y][x])
        for y in range(y1, y2 + 1):
            for x in (x1, x2):
                border_pixels += 1
                dark_border_pixels += int(dark[y][x])
        return dark_border_pixels / max(border_pixels, 1)

    def _merge_overlapping_rectangles(self, rectangles: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
        merged: list[tuple[int, int, int, int]] = []
        for rectangle in sorted(rectangles, key=lambda item: (item[1], item[0])):
            if any(self._rectangle_overlap_ratio(rectangle, existing) > 0.75 for existing in merged):
                continue
            merged.append(rectangle)
        return merged

    def _rectangle_overlap_ratio(self, first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
        ax1, ay1, ax2, ay2 = first
        bx1, by1, bx2, by2 = second
        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)
        if ix2 < ix1 or iy2 < iy1:
            return 0.0
        intersection = (ix2 - ix1 + 1) * (iy2 - iy1 + 1)
        first_area = (ax2 - ax1 + 1) * (ay2 - ay1 + 1)
        second_area = (bx2 - bx1 + 1) * (by2 - by1 + 1)
        return intersection / max(min(first_area, second_area), 1)

    def _text_inside_rectangle(self, word_boxes: list[_OCRWordBox], x1: int, y1: int, x2: int, y2: int) -> str:
        words: list[tuple[int, int, str]] = []
        for box in word_boxes:
            center_x = box["left"] + box["width"] // 2
            center_y = box["top"] + box["height"] // 2
            if x1 <= center_x <= x2 and y1 <= center_y <= y2:
                words.append((box["top"], box["left"], box["text"]))
        return " ".join(word for _, _, word in sorted(words))

    def _dedupe_segments(self, segments: list[tuple[str, int, int, int, int]]) -> list[tuple[str, int, int, int, int]]:
        deduped: list[tuple[str, int, int, int, int]] = []
        for segment in sorted(segments, key=lambda item: (item[0], item[2], item[1], item[3], item[4])):
            if any(self._similar_segment(segment, existing) for existing in deduped):
                continue
            deduped.append(segment)
        return deduped

    def _similar_segment(
        self,
        first: tuple[str, int, int, int, int],
        second: tuple[str, int, int, int, int],
    ) -> bool:
        if first[0] != second[0]:
            return False
        _, ax1, ay1, ax2, ay2 = first
        _, bx1, by1, bx2, by2 = second
        return abs(ax1 - bx1) <= 2 and abs(ay1 - by1) <= 2 and abs(ax2 - bx2) <= 2 and abs(ay2 - by2) <= 2

    def _nearest_endpoint_boxes(
        self,
        boxes: list[_DiagramBox],
        x1: int,
        y1: int,
        x2: int,
        y2: int,
    ) -> tuple[str | None, str | None]:
        if len(boxes) < 2:
            return None, None
        first = self._nearest_box_id(boxes, x1, y1)
        second = self._nearest_box_id(boxes, x2, y2)
        if first == second:
            return None, None
        return first, second

    def _nearest_box_id(self, boxes: list[_DiagramBox], x: int, y: int) -> str | None:
        best_id: str | None = None
        best_distance = float("inf")
        for box in boxes:
            center_x = box["x"] + box["width"] // 2
            center_y = box["y"] + box["height"] // 2
            distance = ((center_x - x) ** 2 + (center_y - y) ** 2) ** 0.5
            threshold = max(box["width"], box["height"]) * 1.5
            if distance < best_distance and distance <= threshold:
                best_distance = distance
                best_id = box["id"]
        return best_id

    def _infer_connector_direction(
        self,
        orientation: str,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        from_box_id: str | None,
        to_box_id: str | None,
    ) -> str:
        if from_box_id is not None and to_box_id is not None:
            if orientation == "horizontal":
                return "left_to_right" if x1 <= x2 else "right_to_left"
            return "top_to_bottom" if y1 <= y2 else "bottom_to_top"
        return "unknown"

    def _edge_density(self, img: Any) -> float:
        try:
            from PIL import ImageFilter

            gray = img.convert("L")
            edge_map = gray.filter(ImageFilter.FIND_EDGES)
            histogram = edge_map.histogram()
            strong_edges = sum(histogram[160:])
            total_pixels = sum(histogram)
            return float(strong_edges) / float(max(total_pixels, 1))
        except Exception:
            return 0.0
