import io
import math
import re
from sqlalchemy import or_
from ..models import KnowledgeSource, now
from ..permissions import rows
from ..store import audit


def extract(filename, data):
    if len(data) > 5 * 1024 * 1024:
        raise ValueError('Documents must be at most 5 MB.')
    if filename.lower().endswith('.pdf'):
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted or len(reader.pages) > 100:
                raise ValueError('Use an unencrypted PDF with at most 100 pages.')
            text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        except Exception:
            raise ValueError('The PDF could not be read. Use a searchable PDF or upload text.') from None
    elif filename.lower().endswith(('.txt', '.md')):
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError('Text documents must use UTF-8.') from None
    else:
        raise ValueError('Upload a PDF, TXT or Markdown document.')
    if not text.strip() or len(text) > 500000:
        raise ValueError('The document must contain searchable text, up to 500,000 characters.')
    return text


def index(source):
    text = source.content
    source.chunks = [{'number': n + 1, 'text': text[start:start + 1800]}
                     for n, start in enumerate(range(0, len(text), 1500))]
    source.updated_at = now()


def upload_document(db, scope, title, filename, data, application=None, audience='staff', global_doc=False):
    scope.require(action='create')
    title = str(title or '').strip()
    if not 1 <= len(title) <= 255:
        raise ValueError('Provide a document title up to 255 characters.')
    if audience not in ('staff', 'customer'):
        raise ValueError('Audience must be staff or customer.')
    app_scope = (application or scope.application or 'erp').lower().strip()
    if app_scope not in ('erp', 'eship', 'global'):
        raise ValueError('Application scope must be erp, eship, or global.')
    target_company_id = scope.company_id
    if global_doc or app_scope == 'global':
        if (scope.user or {}).get('role') != 'super_admin':
            raise PermissionError('Only platform super administrators can upload global Qiyadah documentation.')
        target_company_id = '__global__'
        app_scope = 'global'
    elif app_scope != scope.application and (scope.user or {}).get('role') != 'super_admin':
        app_scope = scope.application

    text = extract(filename, data)
    source = KnowledgeSource(
        company_id=target_company_id,
        title=title,
        application=app_scope,
        audience=audience,
        filename=str(filename or 'document.txt')[:255],
        content=text,
        active=True,
    )
    index(source)
    db.add(source)
    db.flush()
    audit(db, scope, 'knowledge.uploaded', source.id, title=title, application=app_scope, audience=audience)
    db.commit()
    return source


def reindex_document(db, scope, source_id):
    scope.require(action='edit')
    source = rows(db, KnowledgeSource, scope).filter_by(id=str(source_id)).first()
    if not source and (scope.user or {}).get('role') == 'super_admin':
        source = db.query(KnowledgeSource).filter_by(id=str(source_id), company_id='__global__').first()
    if not source:
        raise ValueError('Knowledge document not found.')
    index(source)
    audit(db, scope, 'knowledge.reindexed', source.id, title=source.title)
    db.commit()
    return source


def delete_document(db, scope, source_id):
    scope.require(action='delete')
    source = rows(db, KnowledgeSource, scope).filter_by(id=str(source_id)).first()
    if not source and (scope.user or {}).get('role') == 'super_admin':
        source = db.query(KnowledgeSource).filter_by(id=str(source_id), company_id='__global__').first()
    if not source:
        raise ValueError('Knowledge document not found.')
    doc_id, title = source.id, source.title
    db.delete(source)
    audit(db, scope, 'knowledge.deleted', doc_id, title=title)
    db.commit()
    return {'deleted': True, 'id': doc_id}


def search(db, scope, question, audience='staff'):
    scope.require()
    if audience not in ('staff', 'customer'):
        raise ValueError('Invalid audience.')
    terms = set(re.findall(r'\w{2,}', question.casefold()))
    query = db.query(KnowledgeSource).filter(
        or_(KnowledgeSource.company_id == scope.company_id,
            KnowledgeSource.company_id == '__global__'),
        KnowledgeSource.active.is_(True),
        KnowledgeSource.application.in_((scope.application, 'global')))
    if audience == 'customer':
        query = query.filter_by(audience='customer')
    hits = []
    for source in query:
        for chunk in (source.chunks or []):
            words = set(re.findall(r'\w{2,}', chunk['text'].casefold()))
            overlap = terms & words
            if overlap:
                score = len(overlap) / math.sqrt(max(len(words), 1))
                hits.append((score, {'source_id': source.id, 'title': source.title,
                                    'chunk': chunk['number'], 'text': chunk['text']}))
    return [hit for _, hit in sorted(hits, key=lambda item: item[0], reverse=True)[:5]]
