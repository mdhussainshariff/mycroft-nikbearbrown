-- PROCEDURE 3: Generate Rolling Forecast
-- Extracted from the original 1.Main.sql monolith; deployed via manifest.yaml.

CREATE OR REPLACE PROCEDURE Planning.usp_GenerateRollingForecast(
    base_budget_header_id INT,
    forecast_months INT,
    base_fiscal_year SMALLINT,
    base_fiscal_month TINYINT,
    growth_rate_pct DECIMAL DEFAULT 0.0,
    seasonal_adjustment_mode VARCHAR DEFAULT 'NONE',
    apply_adjustments BOOLEAN DEFAULT TRUE
)
RETURNS VARIANT
LANGUAGE SQL
AS
$$
DECLARE
    v_start_time TIMESTAMP_NTZ := CURRENT_TIMESTAMP();
    v_periods_created INT := 0;
    v_total_forecast DECIMAL(19,4) := 0;
    v_current_month INT;
    v_current_year SMALLINT;
    v_result_json VARIANT;
    EX_INVALID_FORECAST_MONTHS EXCEPTION (-20002, 'Forecast months must be between 1 and 60');
BEGIN
    IF (forecast_months <= 0 OR forecast_months > 60) THEN
        RAISE EX_INVALID_FORECAST_MONTHS;
    END IF;
    
    v_current_year := base_fiscal_year;
    v_current_month := base_fiscal_month;
    
    FOR month_offset IN 1 TO forecast_months DO
        IF (v_current_month = 12) THEN
            v_current_month := 1;
            v_current_year := v_current_year + 1;
        ELSE
            v_current_month := v_current_month + 1;
        END IF;
        
        v_periods_created := v_periods_created + 1;
        v_total_forecast := v_total_forecast + 100000;
    END FOR;
    
    v_result_json := OBJECT_CONSTRUCT(
        'forecast_start', v_start_time,
        'forecast_end', CURRENT_TIMESTAMP(),
        'periods_generated', v_periods_created,
        'total_forecast_amount', v_total_forecast,
        'growth_rate_pct', :growth_rate_pct
    );
    
    RETURN v_result_json;
END;
$$;
