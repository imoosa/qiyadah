import unittest
import json
from bi.builder import validate_layout, CHART_STYLES, STYLES, TREND_STYLES, CATEGORY_STYLES

class TestBIBuilderAdv(unittest.TestCase):
    def test_business_filters_and_table_colours_round_trip(self):
        for key in ('date_range', 'client_id', 'employee_id', 'supplier_id', 'country', 'product_category', 'expense_category'):
            widgets = [dict(id='filter', type='filter', key=key, style='default', x=0, y=0, w=8, h=4),
                       dict(id='table', type='table', key='top_customers', style='default', x=8, y=0, w=10, h=6,
                            card_color='#112233', text_color='#abcdef', value_color='#fedcba')]
            _, _, serial = validate_layout(dict(title='Filters', visibility='private', grid_columns=24,
                                                widgets=widgets, filters={'client_id': '7'}))
            saved = json.loads(serial)
            self.assertEqual(saved['widgets'][0]['key'], key)
            for prop in ('card_color', 'text_color', 'value_color'):
                self.assertEqual(saved['widgets'][1][prop], widgets[1][prop])
            self.assertEqual(saved['filters']['client_id'], '7')

    def test_chart_formatting_round_trip(self):
        formatting = dict(chart_scale=135, donut_hole=45, label_position='outside',
                          label_mode='category_value', axis_label_mode='abbreviate', category_colors={'customer-1': '#ff0033'},
                          series_colors={'subtotal': '#0033ff'}, chart_color='#112233', grid_color='#abcdef',
                          data_label_font_size=24, data_label_color='#ffffff')
        widget = dict(id='chart', type='chart', key='top_customers', style='donut',
                      x=0, y=0, w=12, h=6, **formatting)
        _, _, serial = validate_layout(dict(title='Colors', visibility='private',
                                            grid_columns=24, widgets=[widget]))
        saved = json.loads(serial)['widgets'][0]
        for key, value in formatting.items():
            self.assertEqual(saved[key], value)

    def test_invalid_chart_formatting_is_rejected(self):
        from bi.builder import BIValidationError
        for field, value in [('chart_scale', 200), ('donut_hole', float('nan')),
                             ('label_position', 'invalid'), ('axis_label_mode', 'invalid'), ('chart_color', 'red'), ('grid_color', 'invalid'),
                             ('category_colors', {'x': 'url(evil)'}),
                             ('series_colors', []), ('data_label_font_size', True)]:
            widget = dict(id='chart', type='chart', key='top_customers', style='pie',
                          x=0, y=0, w=12, h=6)
            widget[field] = value
            with self.subTest(field=field), self.assertRaises(BIValidationError):
                validate_layout(dict(title='Colors', visibility='private',
                                     grid_columns=24, widgets=[widget]))

    def test_fractional_layout_survives_save(self):
        widget = dict(id='position', type='metric', key='net_sales', style='default',
                      x=2.37, y=4.61, w=6.25, h=3.15)
        _, _, serial = validate_layout(dict(title='Position', visibility='private',
                                            grid_columns=24, widgets=[widget]))
        saved = json.loads(serial)['widgets'][0]
        for key in ('x', 'y', 'w', 'h'):
            self.assertEqual(saved[key], widget[key])

    def test_nonfinite_layout_is_rejected(self):
        from bi.builder import BIValidationError
        for value in (float('nan'), float('inf'), True):
            widget = dict(id='position', type='metric', key='net_sales', style='default',
                          x=value, y=0, w=6, h=3)
            with self.assertRaises(BIValidationError):
                validate_layout(dict(title='Position', visibility='private',
                                     grid_columns=24, widgets=[widget]))

    def test_new_chart_styles_validation(self):
        self.assertIn('radar', TREND_STYLES)
        self.assertIn('polar_area', CATEGORY_STYLES)
        self.assertIn('spline_line', CHART_STYLES['custom'])
        self.assertIn('curved_area', CHART_STYLES['custom'])
        self.assertIn('grouped_bar', CHART_STYLES['custom'])

    def test_multi_dataset_period_comparison(self):
        payload = {
            "title": "Multi-Metric Comparison Dashboard",
            "visibility": "private",
            "grid_columns": 24,
            "widgets": [
                {
                    "id": "w_trend_comp",
                    "type": "chart",
                    "key": "trend_comparison",
                    "style": "combo",
                    "x": 0, "y": 0, "w": 12, "h": 6,
                    "compare": "previous_period"
                }
            ]
        }
        title, visibility, serial = validate_layout(payload)
        self.assertEqual(title, "Multi-Metric Comparison Dashboard")
        data = json.loads(serial)
        self.assertEqual(len(data['widgets']), 1)
        self.assertEqual(data['widgets'][0]['compare'], 'previous_period')

    def test_semantic_catalog_tree_and_subtables(self):
        from bi.semantic import catalog_payload, validate_spec, CATALOG
        payload = catalog_payload()
        self.assertIn('tree', payload)
        self.assertIn('sales_items', CATALOG)
        self.assertIn('purchase_items', CATALOG)
        self.assertIn('finance', CATALOG)
        self.assertIn('hr', CATALOG)
        
        # Test sub-table spec validation
        spec = validate_spec({
            'semantic_source': 'sales_items',
            'semantic_measure': 'quantity',
            'semantic_dimension': 'item_name',
            'semantic_aggregation': 'sum'
        })
        self.assertEqual(spec['semantic_source'], 'sales_items')
        self.assertEqual(spec['semantic_measure'], 'quantity')

if __name__ == '__main__':
    unittest.main()
