"""
Product deduplication engine.
THE HARD PROBLEM: Store A calls it "iPhone 15 128GB 5G - Black"
                   Store B calls it "Apple iPhone 15 128GB Black (5G)"
                   Store C calls it "iPhone 15 128GB Midnight"
                   
                   SAME PRODUCT. THREE NAMES.
                   
This is what separates your project from every CRUD tutorial.
"""

import re
from typing import Optional, Tuple
from thefuzz import fuzz
from rapidfuzz import fuzz as rapid_fuzz
from sqlalchemy.orm import Session
from app.models.product import Product
from app.models.alias import ProductAlias
from app.models.store import Store


# Regex patterns for spec extraction
# These extract technical specs from product names
SPEC_PATTERNS = {
    "storage": re.compile(r'(\d+)\s*(GB|TB|MB)', re.IGNORECASE),
    "ram": re.compile(r'(\d+)\s*GB\s*RAM', re.IGNORECASE),
    "color": re.compile(
        r'(black|white|silver|gold|blue|red|green|purple|midnight|'
        r'starlight|space gray|graphite|sierra blue|titanium)',
        re.IGNORECASE
    ),
    "network": re.compile(r'(5G|4G|LTE|Wi-Fi|wifi)', re.IGNORECASE),
    "model_year": re.compile(r'(?:iphone|galaxy|ipad|macbook|air)\s*(\d{1,2})', re.IGNORECASE),
}


class DeduplicationEngine:
    """
    Three-layer matching strategy:
    
    Layer 1: SKU/UPC exact match (100% confidence, instant)
    Layer 2: Fuzzy string similarity (80-95% confidence)  
    Layer 3: Spec extraction + brand/model matching (70-85% confidence)
    
    Each layer is tried in order. First match wins.
    """
    
    def __init__(self, db: Session):
        self.db = db
        
    def normalize(self, name: str) -> str:
        """
        Normalize product name for comparison.
        - Lowercase
        - Remove extra whitespace
        - Remove common filler words
        - Standardize spacing around numbers
        """
        # Lowercase
        normalized = name.lower()
        
        # Remove punctuation (keep spaces)
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        
        # Remove filler words that don't affect product identity
        fillers = [
            'smartphone', 'phone', 'mobile', 'cell', 'cellular',
            'new', 'original', 'genuine', 'official', 'authentic',
            'latest', '2024', '2025', 'edition', 'version',
        ]
        for filler in fillers:
            normalized = re.sub(rf'\b{filler}\b', '', normalized)
        
        # Normalize whitespace
        normalized = ' '.join(normalized.split())
        
        return normalized
    
    def extract_specs(self, name: str) -> dict:
        """
        Extract technical specifications from product name.
        Returns dict like: {"storage": "128gb", "color": "black", "network": "5g"}
        """
        specs = {}
        
        for spec_name, pattern in SPEC_PATTERNS.items():
            match = pattern.search(name)
            if match:
                specs[spec_name] = match.group(1).lower() if spec_name != "color" else match.group(1).lower()
                
        return specs
    
    def extract_brand_model(self, name: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract brand and model from product name.
        Returns: (brand, model)
        """
        name_lower = name.lower()
        
        # Brand detection
        brands = {
            'apple': ['iphone', 'ipad', 'macbook', 'airpods', 'watch', 'apple'],
            'samsung': ['galaxy', 'samsung'],
            'sony': ['sony', 'playstation'],
            'lg': ['lg'],
            'huawei': ['huawei'],
            'xiaomi': ['xiaomi', 'redmi', 'poco'],
        }
        
        detected_brand = None
        for brand, keywords in brands.items():
            if any(kw in name_lower for kw in keywords):
                detected_brand = brand
                break
        
        # Model detection (iPhone 15, Galaxy S24, etc.)
        model_patterns = [
            r'iphone\s*(\d{1,2}(?:\s*pro(?:\s*max)?)?)',
            r'galaxy\s*s?(\d{1,2}(?:\s*plus|\s*ultra)?)',
            r'ipad\s*(pro|air|mini)?\s*(\d{1,2})?',
            r'macbook\s*(pro|air)?\s*(\d{1,2})?',
        ]
        
        detected_model = None
        for pattern in model_patterns:
            match = re.search(pattern, name_lower)
            if match:
                detected_model = match.group(0).strip()
                break
                
        return detected_brand, detected_model
    
    def find_match(
        self,
        store_product_name: str,
        store_product_id: Optional[str] = None,
        store_id: Optional[int] = None
    ) -> Tuple[Optional[Product], float, str]:
        """
        Try to match a store product to an existing canonical product.
        
        Returns: (product_or_none, confidence_score, method_used)
        
        Confidence scores:
        1.00 = SKU exact match (certain)
        0.90-0.99 = Fuzzy match > 95 (very likely)
        0.80-0.89 = Fuzzy match > 90 (likely)
        0.70-0.79 = Spec extraction match (possible, needs review)
        0.00 = No match found
        """
        
        # === LAYER 1: SKU Exact Match ===
        if store_product_id:
            existing_alias = (
                self.db.query(ProductAlias)
                .filter(ProductAlias.store_product_id == store_product_id)
                .first()
            )
            if existing_alias:
                return existing_alias.product, 1.0, "sku"
        
        # === LAYER 2: Fuzzy String Matching ===
        normalized_input = self.normalize(store_product_name)
        
        # Get all existing aliases for fuzzy comparison
        all_aliases = self.db.query(ProductAlias).all()
        
        best_match = None
        best_score = 0
        
        for alias in all_aliases:
            normalized_existing = self.normalize(alias.store_product_name)
            
            # Use rapidfuzz (faster, pure Python)
            score = rapid_fuzz.ratio(normalized_input, normalized_existing)
            
            if score > best_score:
                best_score = score
                best_match = alias
        
        # Thresholds for auto-acceptance
        if best_score >= 95:
            return best_match.product, best_score / 100, "fuzzy"
        
        # === LAYER 3: Spec Extraction + Brand/Model ===
        input_specs = self.extract_specs(store_product_name)
        input_brand, input_model = self.extract_brand_model(store_product_name)
        
        # Compare with all products
        all_products = self.db.query(Product).all()
        
        for product in all_products:
            # Check brand/model match first
            product_brand, product_model = self.extract_brand_model(product.canonical_name)
            
            if input_brand != product_brand:
                continue  # Different brands = different products
            
            if input_model and product_model and input_model != product_model:
                continue  # Different models = different products
            
            # Check specs match
            product_specs = self.extract_specs(product.canonical_name)
            
            spec_matches = 0
            spec_total = 0
            
            for spec_key in ["storage", "color", "network"]:
                if spec_key in input_specs or spec_key in product_specs:
                    spec_total += 1
                    if input_specs.get(spec_key) == product_specs.get(spec_key):
                        spec_matches += 1
            
            if spec_total > 0 and spec_matches / spec_total >= 0.8:
                # Specs mostly match, but confidence is lower
                return product, 0.75, "spec_extract"
        
        # === NO MATCH ===
        return None, 0.0, "none"
    
    def _find_existing_alias(
        self,
        store_id: int,
        store_product_name: str,
        store_product_id: Optional[str] = None,
    ) -> Optional[ProductAlias]:
        """
        Look up the alias this exact store listing already maps to.

        Scoped by store_id: two stores can legitimately reuse the same SKU
        string, so matching on store_product_id alone would cross-link them.
        """
        q = self.db.query(ProductAlias).filter(ProductAlias.store_id == store_id)
        if store_product_id:
            hit = q.filter(ProductAlias.store_product_id == store_product_id).first()
            if hit:
                return hit
        return q.filter(
            ProductAlias.store_product_name == store_product_name
        ).first()

    def create_alias(
        self,
        product_id: int,
        store_id: int,
        store_product_name: str,
        store_product_id: Optional[str] = None,
        store_product_url: Optional[str] = None,
        confidence: float = 0.0,
        method: str = "manual"
    ) -> ProductAlias:
        """
        Create a new alias mapping a store product to a canonical product.
        """
        alias = ProductAlias(
            product_id=product_id,
            store_id=store_id,
            store_product_name=store_product_name,
            store_product_id=store_product_id,
            store_product_url=store_product_url,
            match_confidence=confidence,
            match_method=method
        )
        self.db.add(alias)
        self.db.commit()
        self.db.refresh(alias)
        return alias
    
    def process_new_product(
        self,
        store_id: int,
        store_product_name: str,
        store_product_id: Optional[str] = None,
        store_product_url: Optional[str] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None
    ) -> Tuple[Product, ProductAlias, bool]:
        """
        Main entry point: Process a new product from a store.
        
        1. Try to match existing product
        2. If match found, create alias linking to existing
        3. If no match, create new canonical product + alias
        
        Returns: (product, alias, is_new_product)
        """
        # IDEMPOTENCY GUARD -- must run before anything else.
        # The scraper re-processes every listing on every run. Without this
        # check, a listing we have already seen still fell through to
        # create_alias() below and inserted a DUPLICATE alias, which in turn
        # made the scraper insert a duplicate Price row. Four scrape runs =
        # four aliases and four prices for one product at one store, so
        # store_count inflated and PriceHistory never recorded a change.
        existing_alias = self._find_existing_alias(
            store_id, store_product_name, store_product_id
        )
        if existing_alias:
            return existing_alias.product, existing_alias, False

        # Try to find existing match
        existing_product, confidence, method = self.find_match(
            store_product_name,
            store_product_id,
            store_id
        )
        
        if existing_product:
            # Link to existing product
            alias = self.create_alias(
                product_id=existing_product.id,
                store_id=store_id,
                store_product_name=store_product_name,
                store_product_id=store_product_id,
                store_product_url=store_product_url,
                confidence=confidence,
                method=method
            )
            return existing_product, alias, False
        
        # No match — create new canonical product
        # Extract brand from name if not provided
        if not brand:
            detected_brand, _ = self.extract_brand_model(store_product_name)
            brand = detected_brand or "Unknown"
        
        # Generate canonical name (normalized version)
        canonical_name = self.normalize(store_product_name)
        
        # Extract specs for storage
        specs = self.extract_specs(store_product_name)
        
        new_product = Product(
            canonical_name=canonical_name,
            brand=brand,
            category=category or "Uncategorized",
            specs=specs
        )
        self.db.add(new_product)
        self.db.commit()
        self.db.refresh(new_product)
        
        # Create alias for this store's naming
        alias = self.create_alias(
            product_id=new_product.id,
            store_id=store_id,
            store_product_name=store_product_name,
            store_product_id=store_product_id,
            store_product_url=store_product_url,
            confidence=1.0,  # First alias is the definition
            method="manual"
        )
        
        return new_product, alias, True