import json
from collections.abc import Callable
from typing import Any, Literal
from urllib.parse import unquote, unquote_plus

from fastapi_filter.contrib.sqlalchemy.filter import Filter as _Filter
from fastapi_filter.contrib.sqlalchemy.filter import _orm_operator_transformer
from pydantic import Field, field_validator
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Query
from sqlalchemy.sql.selectable import Select


class Filter(_Filter):
    """
    Base filter class with full text search capability based on fastapi-filter's SQLAlchemy Filter.
    """

    search: str | None = Field(default=None, description="Perform a full text search on the model")

    _ORM_OPERATORS: dict[str, Callable[[Any], tuple[str, Any]]] = {
        "contains": lambda value: ("any", value),
        "jsonb_contains": lambda value: ("op_jsonb_contains", value),
        "jsonb_has_key": lambda value: ("op_jsonb_has_key", value),
        "jsonb_has_any_key": lambda value: ("op_jsonb_has_any_key", value),
        "jsonb_has_all_keys": lambda value: ("op_jsonb_has_all_keys", value),
        "jsonb_path_eq": lambda value: ("op_jsonb_path_eq", value),
        "jsonb_path_ne": lambda value: ("op_jsonb_path_ne", value),
        "jsonb_path_gt": lambda value: ("op_jsonb_path_gt", value),
        "jsonb_path_gte": lambda value: ("op_jsonb_path_gte", value),
        "jsonb_path_lt": lambda value: ("op_jsonb_path_lt", value),
        "jsonb_path_lte": lambda value: ("op_jsonb_path_lte", value),
        "jsonb_path_in": lambda value: ("op_jsonb_path_in", value),
        "jsonb_path_like": lambda value: ("op_jsonb_path_like", value),
        "jsonb_path_ilike": lambda value: ("op_jsonb_path_ilike", value),
        **_orm_operator_transformer,
    }

    @staticmethod
    def _parse_jsonb_path_value(value: str) -> tuple[str, str]:
        """
        Parse a JSONB path value string in the format 'key:value' or 'path.to.key:value'.

        Parameters
        ----------
        value: String in format 'key:value' or 'nested.key:value' (may be URL-encoded)

        Returns
        -------
        Tuple of (path, value)

        Examples
        --------

            ```
            'profession:engineer' -> ('profession', 'engineer')
            'address.city:New York' -> ('address.city', 'New York')
            'profession:software+engineer' -> ('profession', 'software engineer')
            'title:Senior%20Developer' -> ('title', 'Senior Developer')
            'profession%3Aengineer' -> ('profession', 'engineer')  # colon encoded as %3A
            'title%3ASenior+Developer' -> ('title', 'Senior Developer')  # both colon and space encoded
            ```
        """

        decoded_value = unquote(unquote_plus(value))

        if ":" not in decoded_value:
            raise ValueError(f"JSONB path value must be in format 'key:value' or 'path.to.key:value', got: {value}")

        path, val = decoded_value.split(":", 1)
        return path.strip(), val.strip()

    @staticmethod
    def _parse_jsonb_path_list(value: str) -> tuple[str, list[str]]:
        """
        Parse a JSONB path list value string in the format 'key:value1,value2,value3'.

        Parameters
        ----------
        value: String in format 'key:val1,val2' or 'nested.key:val1,val2' (may be URL-encoded)

        Returns
        -------
        Tuple of (path, list of values)

        Examples
        ---------

            ```
            'profession:engineer,developer' -> ('profession', ['engineer', 'developer'])
            'city%3ANew+York,Los+Angeles' -> ('city', ['New York', 'Los Angeles'])  # colon and spaces encoded
            ```
        """

        decoded_value = unquote(unquote_plus(value))

        if ":" not in decoded_value:
            raise ValueError(f"JSONB path value must be in format 'key:value1,value2', got: {value}")

        path, vals = decoded_value.split(":", 1)
        return path.strip(), [v.strip() for v in vals.split(",")]

    class Constants(_Filter.Constants):
        default_order_by: str
        allowed_sort_fields: Literal["__all__"] | list[str] = []
        original_filter: type["Filter"]  # type: ignore[misc, valid-type]
        search_trgm_fields: list[str] = []

    def filter(self, query: Query[Any] | Select[Any]) -> Query[Any] | Select[Any]:
        for field_name, value in self.filtering_fields:
            field_value = getattr(self, field_name)
            if isinstance(field_value, Filter):
                query = field_value.filter(query)
            else:
                if "__" in field_name:
                    field_name, operator = field_name.split("__", 1)
                    # Check if operator contains another __ (e.g., "id__in" from "categories__id__in")
                    # This indicates a relationship filter pattern like: relationship__field__operator
                    # or nested relationships: directory__categories__id__in
                    if "__" in operator:
                        # Parse the relationship chain
                        # For directory__categories__id__in:
                        #   - relationship_name = "directory"
                        #   - remaining = "categories__id__in"
                        relationship_name = field_name
                        remaining = operator

                        # Start with the first relationship
                        current_model = self.Constants.model
                        relationship_attr = getattr(current_model, relationship_name)
                        query = query.join(relationship_attr)
                        current_model = relationship_attr.property.mapper.class_

                        # Process remaining parts (could be nested relationships)
                        parts = remaining.split("__")

                        # Check if we have nested relationships
                        # Pattern: field1__field2__...__operator
                        # We need to determine where relationships end and field+operator begin
                        # Strategy: work backwards - last two parts are field + operator
                        # Everything before that is relationships

                        if len(parts) >= 2:
                            # Check if this is a nested relationship (more than 2 parts)
                            # or just field__operator (2 parts)
                            if len(parts) > 2:
                                # Nested relationships: join through each one
                                # e.g., categories__id__in -> join categories, then filter on id
                                for i in range(len(parts) - 2):
                                    next_rel_name = parts[i]
                                    relationship_attr = getattr(current_model, next_rel_name)
                                    query = query.join(relationship_attr)
                                    current_model = relationship_attr.property.mapper.class_

                                # Now handle the final field + operator
                                related_field = parts[-2]
                                actual_operator = parts[-1]
                            else:
                                # Simple case: just field__operator
                                related_field = parts[0]
                                actual_operator = parts[1]

                            # Transform operator (e.g., "in" -> ("in_", value))
                            actual_operator, value = self._ORM_OPERATORS[actual_operator](value)

                            # Apply filter on the final field
                            related_model_field = getattr(current_model, related_field)

                            # Handle JSONB operators specially
                            if actual_operator == "op_jsonb_contains":
                                if isinstance(value, str):
                                    try:
                                        value = json.loads(value)
                                    except json.JSONDecodeError:
                                        raise ValueError(f"Invalid JSON for jsonb_contains: {value}")
                                query = query.filter(related_model_field.op("@>")(value))

                            elif actual_operator == "op_jsonb_has_key":
                                query = query.filter(related_model_field.op("?")(value))

                            elif actual_operator == "op_jsonb_has_any_key":
                                keys = value if isinstance(value, list) else value.split(",")
                                query = query.filter(related_model_field.op("?|")(keys))

                            elif actual_operator == "op_jsonb_has_all_keys":
                                keys = value if isinstance(value, list) else value.split(",")
                                query = query.filter(related_model_field.op("?&")(keys))

                            elif actual_operator.startswith("op_jsonb_path_"):
                                if actual_operator == "op_jsonb_path_in":
                                    path, values = self._parse_jsonb_path_list(value)
                                    json_value = None
                                else:
                                    path, json_value = self._parse_jsonb_path_value(value)
                                    values = None

                                path_parts = path.split(".")
                                jsonb_expr = related_model_field

                                for part in path_parts[:-1]:
                                    jsonb_expr = jsonb_expr.op("->")(part)

                                final_key = path_parts[-1]
                                text_value = jsonb_expr.op("->>")(final_key)

                                if actual_operator == "op_jsonb_path_eq":
                                    query = query.filter(text_value == json_value)
                                elif actual_operator == "op_jsonb_path_ne":
                                    query = query.filter(text_value != json_value)
                                elif actual_operator == "op_jsonb_path_gt":
                                    query = query.filter(cast(text_value, String) > json_value)
                                elif actual_operator == "op_jsonb_path_gte":
                                    query = query.filter(cast(text_value, String) >= json_value)
                                elif actual_operator == "op_jsonb_path_lt":
                                    query = query.filter(cast(text_value, String) < json_value)
                                elif actual_operator == "op_jsonb_path_lte":
                                    query = query.filter(cast(text_value, String) <= json_value)
                                elif actual_operator == "op_jsonb_path_in":
                                    query = query.filter(text_value.in_(values))
                                elif actual_operator == "op_jsonb_path_like":
                                    query = query.filter(text_value.like(json_value))
                                elif actual_operator == "op_jsonb_path_ilike":
                                    query = query.filter(text_value.ilike(json_value))

                            else:
                                query = query.filter(getattr(related_model_field, actual_operator)(value))
                        else:
                            # Edge case: only one part after relationship, treat as field name
                            related_field = parts[0]
                            if getattr(current_model, related_field) is not None:
                                query = query.filter(getattr(current_model, related_field) == value)

                        continue

                    operator, value = self._ORM_OPERATORS[operator](value)
                else:
                    operator = "__eq__"

                if field_name == self.Constants.search_field_name:
                    if (
                        hasattr(self.Constants.model, "search_vector")
                        and hasattr(self.Constants, "search_trgm_fields")
                        and len(self.Constants.search_trgm_fields) > 0
                    ):
                        # if model has search_vector and trigram fields defined, use a combination of FTS and trigram similarity for better search results
                        language = getattr(self.Constants, "search_vector_language", "english")
                        search_query = " & ".join(value.strip().split())
                        fts_filter = self.Constants.model.search_vector.op("@@")(
                            func.to_tsquery(language, search_query)
                        )
                        trgm_expr = func.concat_ws(
                            " ",
                            *[getattr(self.Constants.model, f) for f in self.Constants.search_trgm_fields],
                        )
                        trgm_filter = func.similarity(trgm_expr, value) > 0.3
                        query = query.filter(or_(fts_filter, trgm_filter))
                    elif hasattr(self.Constants.model, "search_vector"):
                        # If the model has only search_vector defined, use full-text search
                        language = getattr(self.Constants, "search_vector_language", "english")
                        search_query = " & ".join(value.strip().split())
                        fts_filter = self.Constants.model.search_vector.op("@@")(
                            func.to_tsquery(language, search_query)
                        )
                        query = query.filter(fts_filter)
                    elif hasattr(self.Constants, "search_trgm_fields") and len(self.Constants.search_trgm_fields) > 0:
                        # If no search_vector but trigram fields are defined, use ilike on those fields
                        search_filters = [
                            getattr(self.Constants.model, field).ilike(f"%{value}%")
                            for field in self.Constants.search_trgm_fields
                        ]
                        query = query.filter(or_(*search_filters))
                    elif hasattr(self.Constants, "search_model_fields"):
                        # Fallback to ilike search for models without search_vector
                        search_filters = [
                            getattr(self.Constants.model, field).ilike(f"%{value}%")
                            for field in self.Constants.search_model_fields
                        ]
                        query = query.filter(or_(*search_filters))
                else:
                    model_field = getattr(self.Constants.model, field_name)

                    if operator == "op_jsonb_contains":
                        # @> containment operator - check if JSONB contains the given data
                        if isinstance(value, str):
                            try:
                                value = json.loads(value)
                            except json.JSONDecodeError:
                                raise ValueError(f"Invalid JSON for jsonb_contains: {value}")
                        query = query.filter(model_field.op("@>")(value))

                    elif operator == "op_jsonb_has_key":
                        # ? operator - check if JSONB has a specific key
                        query = query.filter(model_field.op("?")(value))

                    elif operator == "op_jsonb_has_any_key":
                        # ?| operator - check if JSONB has any of the specified keys
                        keys = value if isinstance(value, list) else value.split(",")
                        query = query.filter(model_field.op("?|")(keys))

                    elif operator == "op_jsonb_has_all_keys":
                        # ?& operator - check if JSONB has all of the specified keys
                        keys = value if isinstance(value, list) else value.split(",")
                        query = query.filter(model_field.op("?&")(keys))

                    elif operator.startswith("op_jsonb_path_"):
                        if operator == "op_jsonb_path_in":
                            path, values = self._parse_jsonb_path_list(value)
                            json_value = None
                        else:
                            path, json_value = self._parse_jsonb_path_value(value)
                            values = None

                        path_parts = path.split(".")
                        jsonb_expr = model_field

                        for part in path_parts[:-1]:
                            jsonb_expr = jsonb_expr.op("->")(part)

                        final_key = path_parts[-1]
                        text_value = jsonb_expr.op("->>")(final_key)

                        if operator == "op_jsonb_path_eq":
                            query = query.filter(text_value == json_value)
                        elif operator == "op_jsonb_path_ne":
                            query = query.filter(text_value != json_value)
                        elif operator == "op_jsonb_path_gt":
                            query = query.filter(cast(text_value, String) > json_value)
                        elif operator == "op_jsonb_path_gte":
                            query = query.filter(cast(text_value, String) >= json_value)
                        elif operator == "op_jsonb_path_lt":
                            query = query.filter(cast(text_value, String) < json_value)
                        elif operator == "op_jsonb_path_lte":
                            query = query.filter(cast(text_value, String) <= json_value)
                        elif operator == "op_jsonb_path_in":
                            query = query.filter(text_value.in_(values))
                        elif operator == "op_jsonb_path_like":
                            query = query.filter(text_value.like(json_value))
                        elif operator == "op_jsonb_path_ilike":
                            query = query.filter(text_value.ilike(json_value))

                    else:
                        query = query.filter(getattr(model_field, operator)(value))

        return query

    def sort(self, query: Query | Select) -> Query | Select:
        query = super().sort(query)

        if not self.ordering_values:
            return query

        order_fields = [field.lstrip("+-") for field in self.ordering_values]
        if "id" in order_fields:
            return query

        id_field = getattr(self.Constants.model, "id", None)
        if id_field is None:
            return query

        direction = self.Direction.desc if self.ordering_values[-1].startswith("-") else self.Direction.asc
        return query.order_by(getattr(id_field, direction)())

    def to_cache_key(self) -> str:
        """
        Generate a cache key based on the filter fields and values.
        """

        key_parts = []
        for field_name, value in self.filtering_fields:
            field_value = getattr(self, field_name)
            if isinstance(field_value, Filter):
                nested_key = field_value.to_cache_key()
                key_parts.append(f"{field_name}({nested_key})")
            else:
                key_parts.append(f"{field_name}:{value}")

        key = "|".join(key_parts)

        return key.encode("utf-8").hex()

    @field_validator("order_by", check_fields=False)
    def restrict_sortable_fields(cls, value: list[str] | None) -> list[str]:
        if value is None:
            return [cls.Constants.default_order_by]

        allowed_sort_fields = cls.Constants.allowed_sort_fields

        if isinstance(allowed_sort_fields, str) and allowed_sort_fields == "__all__":
            return value

        for field_name in value:
            field_name = field_name.replace("+", "").replace("-", "")  #
            if field_name not in cls.Constants.allowed_sort_fields:
                raise ValueError(
                    f"`{field_name}` is not a valid ordering field. "
                    f"You may only sort by: {', '.join(cls.Constants.allowed_sort_fields)}"
                )

        return value
