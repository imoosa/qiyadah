"""CRM workspace regression tests using an isolated in-memory database."""
import unittest
from datetime import date, timedelta
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from customer_models import (Client, CRMContact, CRMLead, CRMInteraction, CRMProject,
                             CRMSetting, CRMQuotation, CRMCommunicationLog, OrderFlow, OrderFlowHistory)
from crm_routes import register_crm_routes


class CRMWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        for model in (Client, CRMContact, CRMLead, CRMInteraction, CRMProject,
                      CRMSetting, CRMQuotation, CRMCommunicationLog, OrderFlow, OrderFlowHistory):
            model.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.user = {'role': 'owner', 'full_name': 'Test Owner'}
        app = Flask(__name__)
        app.testing = True
        register_crm_routes(app, lambda f:f, lambda:self.db, lambda:'A', lambda:self.user, lambda c:None)
        self.client = app.test_client()
        self.db.add_all([Client(id=1, company_id='A', name='Our account'), Client(id=2, company_id='B', name='Other account')])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_project_lifecycle_and_tenant_isolation(self):
        r = self.client.post('/api/crm/projects', json={'name':'Service project','client_id':'1'})
        self.assertEqual(r.status_code, 201)
        ident = r.json['project']['id']
        self.db.add(CRMProject(id='foreign', company_id='B', name='Private'))
        self.db.commit()
        self.assertEqual(len(self.client.get('/api/crm/projects').json['projects']), 1)
        self.assertEqual(self.client.put('/api/crm/projects/foreign', json={'name':'Changed'}).status_code, 404)
        r = self.client.put('/api/crm/projects/'+ident, json={'name':'Service project','status':'Archived','client_id':'1'})
        self.assertEqual(r.json['project']['status'], 'Archived')
        self.assertEqual(self.client.get('/api/crm/workspace/metrics').json['active_projects'], 0)
        self.assertEqual(self.client.post('/api/crm/projects', json={'name':'Bad','client_id':'2'}).status_code, 404)
        self.assertEqual(self.client.post('/api/crm/projects', json={'name':'Bad','due_date':'invalid'}).status_code, 400)

    def test_activity_form_validation_and_metrics(self):
        due=(date.today()-timedelta(days=1)).isoformat()
        r=self.client.post('/api/crm/activities',json={'type':'call','summary':'Call customer','client_id':'1','due_date':due})
        self.assertEqual(r.status_code,201)
        self.db.add(CRMInteraction(company_id='B',client_id='2',type='task',summary='Private',created_by='Other',due_date=date.today()-timedelta(days=1)))
        self.db.commit()
        metrics=self.client.get('/api/crm/workspace/metrics').json
        self.assertEqual(metrics['scheduled_calls'],1)
        self.assertEqual(metrics['open_tasks'],0)
        self.assertEqual(metrics['overdue'],1)
        self.client.put('/api/crm/activities/'+str(r.json['activity']['id'])+'/toggle')
        self.assertEqual(self.client.get('/api/crm/workspace/metrics').json['overdue'],0)
        self.assertEqual(self.client.post('/api/crm/activities',json={'type':'invalid','summary':'x'}).status_code,400)
        self.assertEqual(self.client.post('/api/crm/activities',json={'summary':'x','client_id':'2'}).status_code,404)
        self.assertEqual(self.client.post('/api/crm/activities',json={'summary':'x','due_date':'bad'}).status_code,400)

    def test_contacts_and_deals(self):
        self.assertEqual(self.client.post('/api/crm/contacts',json={'name':'Alice','client_id':'2'}).status_code,404)
        self.assertEqual(self.client.post('/api/crm/contacts',json={'name':'Alice','client_id':'1'}).status_code,201)
        self.db.add_all([CRMLead(id='new',company_id='A',client_id='1',title='New',stage='New',created_by='Owner'),
                         CRMLead(id='deal',company_id='A',client_id='1',title='Deal',stage='Qualified',created_by='Owner')])
        self.db.commit()
        result=self.client.get('/api/crm/leads?module=deals').json
        self.assertEqual([r['id'] for r in result['leads']], ['deal'])

    def test_setup_permissions_validation_and_persistence(self):
        url='/api/crm/workspace/preferences'
        self.user['role']='employee'
        self.assertEqual(self.client.post(url,json={'show_metrics':False}).status_code,403)
        self.user['role']='owner'
        self.assertEqual(self.client.post(url,json={'chat_widget_url':'javascript:alert(1)'}).status_code,400)
        self.assertEqual(self.client.post(url,json={'chat_enabled':True}).status_code,400)
        self.assertEqual(self.client.post(url,json={'show_metrics':'false'}).status_code,400)
        self.assertEqual(self.client.post(url,json={'show_metrics':False}).status_code,200)
        self.assertEqual(self.client.post(url,json={'chat_widget_url':'https://example.com/widget.js','chat_enabled':True}).status_code,200)
        prefs=self.client.get(url).json['preferences']
        self.assertFalse(prefs['show_metrics'])
        self.assertTrue(prefs['chat_enabled'])
        self.assertEqual(self.db.query(CRMSetting).count(),1)

    def test_export_scope_and_formula_escaping(self):
        self.db.add_all([CRMContact(id='a',company_id='A',client_id='1',name='=1+1'),CRMContact(id='b',company_id='B',client_id='2',name='Private')])
        self.db.commit()
        r=self.client.get('/api/crm/workspace/export/contacts')
        text=r.get_data(as_text=True)
        self.assertIn("'=1+1",text)
        self.assertNotIn('Private',text)
        self.assertEqual(self.client.get('/api/crm/workspace/export/unknown').status_code,404)

if __name__ == '__main__':
    unittest.main()
