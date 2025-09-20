# simple_app.py - Complete Enhanced Version
"""Enhanced Flask app with context-aware chat and improved document matching"""
from services.hr_questions_handler import HRQuestionsHandler, integrate_hr_handler
import os
import json
from datetime import timedelta, datetime, timezone
from flask import Flask, jsonify, session, send_file, request, Response
from flask_cors import CORS
from flask_session import Session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import re

# Import utilities
from utils.database import DatabaseManager

def create_simple_app():
    """Create enhanced Flask application with context awareness"""
    
    # Create Flask app
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_PERMANENT'] = False
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
    app.config['SESSION_COOKIE_NAME'] = 'rag_session'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = False
    
    # Initialize extensions
    Session(app)
    CORS(app, 
         origins=['http://localhost:3000', 'http://127.0.0.1:3000'],
         supports_credentials=True,
         allow_headers=['Content-Type', 'Accept'],
         methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
    )
    
    # Create directories
    os.makedirs('documents', exist_ok=True)
    os.makedirs('chroma_db', exist_ok=True)
    
    # Initialize services with enhanced versions
    from config import get_config
    from services.enhanced_rag_service import EnhancedRAGServiceV2
    from services.enhanced_chat_service import EnhancedChatService
    from services.document_manager import DocumentManager
    from services.contact_db_search import enhance_rag_with_contact_search
    
    config = get_config()
    
    db_manager = DatabaseManager(config.DATABASE_FILE)
    rag_service = EnhancedRAGServiceV2(config, db_manager)
    
    # ENHANCE RAG SERVICE WITH CONTACT DB SEARCH
    rag_service = enhance_rag_with_contact_search(rag_service)
    
    chat_service = EnhancedChatService(db_manager, rag_service, config)

    app = integrate_hr_handler(app, db_manager, rag_service, chat_service)

    doc_manager = DocumentManager(db_manager, config)
    
    # Ensure database columns exist
    try:
        db_manager.execute_query(
            "ALTER TABLE documents ADD COLUMN document_type TEXT DEFAULT 'other'"
        )
    except:
        pass
    
    try:
        db_manager.execute_query(
            "ALTER TABLE documents ADD COLUMN is_template BOOLEAN DEFAULT FALSE"
        )
    except:
        pass
    
    try:
        db_manager.execute_query(
            "ALTER TABLE documents ADD COLUMN keywords TEXT"
        )
    except:
        pass
    
    # ============= AUTH DECORATORS =============
    def login_required(f):
        """Decorator to require login"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'Authentication required'}), 401
            return f(*args, **kwargs)
        return decorated_function
    
    def admin_required(f):
        """Decorator to require admin role"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'Authentication required'}), 401
            if session.get('role') != 'admin':
                return jsonify({'error': 'Admin access required'}), 403
            return f(*args, **kwargs)
        return decorated_function
    
    # ============= AUTH ROUTES =============
    @app.route('/api/auth/register', methods=['POST'])
    def register():
        """Register new user"""
        try:
            data = request.get_json()
            username = data.get('username', '').strip()
            password = data.get('password', '').strip()
            email = data.get('email', '').strip()
            
            # Validation
            if not username or not password:
                return jsonify({'error': 'Username və password tələb olunur'}), 400
            
            if len(username) < 3:
                return jsonify({'error': 'Username ən azı 3 simvol olmalıdır'}), 400
            
            if len(password) < 6:
                return jsonify({'error': 'Password ən azı 6 simvol olmalıdır'}), 400
            
            # Check if user exists
            existing_user = db_manager.get_user_by_username(username)
            if existing_user:
                return jsonify({'error': 'Bu username artıq mövcuddur'}), 400
            
            # Create user
            password_hash = generate_password_hash(password)
            user_id = db_manager.create_user(username, password_hash, email)
            
            # Set session
            session['user_id'] = user_id
            session['username'] = username
            session['role'] = 'user'
            session.permanent = True
            
            return jsonify({
                'message': 'Qeydiyyat uğurlu',
                'user': {
                    'id': user_id,
                    'username': username,
                    'role': 'user',
                    'email': email
                }
            }), 201
            
        except Exception as e:
            return jsonify({'error': f'Qeydiyyat xətası: {str(e)}'}), 500
    
    @app.route('/api/auth/login', methods=['POST'])
    def login():
        """Login user"""
        try:
            data = request.get_json()
            username = data.get('username', '').strip()
            password = data.get('password', '').strip()
            
            if not username or not password:
                return jsonify({'error': 'Username və password tələb olunur'}), 400
            
            # Get user
            user = db_manager.get_user_by_username(username)
            if not user or not check_password_hash(user['password_hash'], password):
                return jsonify({'error': 'Yanlış username və ya password'}), 401
            
            # Set session
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session.permanent = True
            
            return jsonify({
                'message': 'Giriş uğurlu',
                'user': {
                    'id': user['id'],
                    'username': user['username'],
                    'role': user['role'],
                    'email': user.get('email')
                }
            })
            
        except Exception as e:
            return jsonify({'error': f'Login xətası: {str(e)}'}), 500
    
    @app.route('/api/auth/logout', methods=['POST'])
    def logout():
        """Logout user"""
        session.clear()
        return jsonify({'message': 'Çıxış edildi'})
    
    @app.route('/api/auth/check', methods=['GET'])
    def check_auth():
        """Check authentication status"""
        if 'user_id' in session:
            return jsonify({
                'authenticated': True,
                'user': {
                    'id': session['user_id'],
                    'username': session['username'],
                    'role': session.get('role', 'user')
                }
            })
        
        return jsonify({'authenticated': False})
    
    @app.route('/api/auth/me', methods=['GET'])
    @login_required
    def get_current_user():
        """Get current user info"""
        user_id = session['user_id']
        user = db_manager.get_user_by_id(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'user': {
                'id': user['id'],
                'username': user['username'],
                'role': user['role'],
                'email': user.get('email'),
                'created_at': user.get('created_at')
            }
        })
    
    # ============= CHAT ROUTES =============
    @app.route('/api/chat/ask', methods=['POST'])
    @login_required
    def ask_question():
        """Enhanced smart chat endpoint with context awareness and better formatting"""
        data = request.get_json()
        question = data.get('question', '').strip()
        document_id = data.get('document_id')
        conversation_id = data.get('conversation_id')
        
        if not question:
            return jsonify({'error': 'Sual tələb olunur'}), 400
        
        print(f"\n=== CHAT REQUEST ===")
        print(f"Question: {question}")
        print(f"Document ID: {document_id}")
        print(f"Conversation ID: {conversation_id}")
        
        # Handle explicit document selection
        if document_id:
            documents = db_manager.get_documents()
            doc = next((d for d in documents if d['id'] == document_id), None)
            
            if not doc:
                return jsonify({'error': 'Sənəd tapılmadı'}), 404
            
            if not doc.get('is_processed'):
                return jsonify({'error': 'Sənəd hələ işlənməyib'}), 400
            
            print(f"Using explicitly selected document: {doc['original_name']}")
            
            # Use RAG directly with selected document
            result = rag_service.answer_question(question, document_id)
            raw_answer = result.get('answer', 'Cavab tapılmadı')
            
            # Format structured answer
            formatted_answer = chat_service.format_structured_answer(
                raw_answer, question, doc['original_name'], doc.get('document_type', 'other')
            )
            
            # Save conversation
            message = {
                'question': question,
                'answer': formatted_answer,
                'document_id': document_id,
                'document_name': doc['original_name'],
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            if not conversation_id:
                title = f"{doc['original_name']}: {question[:30]}..."
                conversation_id = db_manager.create_conversation(
                    user_id=session['user_id'],
                    document_id=document_id,
                    title=title,
                    messages=json.dumps([message])
                )
            else:
                conv = db_manager.get_conversation(conversation_id, session['user_id'])
                if conv:
                    messages = json.loads(conv['messages'])
                    messages.append(message)
                    db_manager.update_conversation(conversation_id, json.dumps(messages))
            
            return jsonify({
                'answer': formatted_answer,
                'conversation_id': conversation_id,
                'document_used': {
                    'id': doc['id'],
                    'name': doc['original_name']
                },
                'type': 'document_answer'
            })
        
        # Check for template requests - delegate to enhanced chat service
        question_lower = question.lower()
        template_indicators = ['şablon', 'shablon', 'nümunə', 'numune', 'template', 'yüklə', 'yukle', 'download', 'link']
        is_template_request = any(indicator in question_lower for indicator in template_indicators)
        
        if is_template_request:
            # Use enhanced template search from chat service
            template_match = chat_service.find_template_by_keywords(question)
            
            if template_match:
                template_doc = template_match['document']
                template_info = template_match['template_info']
                
                download_url = f"http://localhost:5000/api/documents/{template_doc['id']}/download"
                
                answer = f"""**📄 {template_info['template_name']} şablonu tapıldı!**

**📥 Yükləmə linki:** [Bu linkə klikləyin]({download_url})

**ℹ️ Fayl məlumatları:**
• **Fayl adı:** {template_doc['original_name']}
• **Fayl tipi:** {template_doc['file_type']}
• **Ölçü:** {template_doc['file_size']} bayt

Linkə klikləyərək şablonu kompüterinizə yükləyə bilərsiniz."""
                
                message = {
                    'question': question,
                    'answer': answer,
                    'document_id': template_doc['id'],
                    'document_name': template_doc['original_name'],
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
                
                if not conversation_id:
                    title = f"Şablon: {question[:30]}..."
                    conversation_id = db_manager.create_conversation(
                        user_id=session['user_id'],
                        document_id=template_doc['id'],
                        title=title,
                        messages=json.dumps([message])
                    )
                else:
                    conv = db_manager.get_conversation(conversation_id, session['user_id'])
                    if conv:
                        messages = json.loads(conv['messages'])
                        messages.append(message)
                        db_manager.update_conversation(conversation_id, json.dumps(messages))
                
                return jsonify({
                    'answer': answer,
                    'conversation_id': conversation_id,
                    'document_used': {
                        'id': template_doc['id'],
                        'name': template_doc['original_name']
                    },
                    'type': 'template_download'
                })
            else:
                # No template found - provide helpful message
                answer = f"**Axtardığınız şablon tapılmadı.** 😔\n\nSistemdə mövcud şablonları görmək üçün admin ilə əlaqə saxlayın və ya \"sənədlər\" yazaraq bütün yüklənmiş faylları görə bilərsiniz."
                
                message = {
                    'question': question,
                    'answer': answer,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
                
                if not conversation_id:
                    title = f"Şablon axtarışı: {question[:30]}..."
                    conversation_id = db_manager.create_conversation(
                        user_id=session['user_id'],
                        document_id=None,
                        title=title,
                        messages=json.dumps([message])
                    )
                
                return jsonify({
                    'answer': answer,
                    'conversation_id': conversation_id,
                    'type': 'template_not_found'
                })
        
        # USE CONTEXT-AWARE CHAT SERVICE
        print("Using context-aware chat service...")
        result = chat_service.process_chat_message(
            question=question,
            user_id=session['user_id'],
            conversation_id=conversation_id
        )
        
        return jsonify(result)
    
    # ============= DOCUMENT ROUTES =============
    @app.route('/api/documents', methods=['GET'])
    @login_required
    def list_documents():
        documents = db_manager.get_documents()
        
        return jsonify({
            'documents': [
                {
                    'id': doc['id'],
                    'name': doc['original_name'],
                    'size': doc['file_size'],
                    'type': doc['file_type'],
                    'document_type': doc.get('document_type', 'other'),
                    'uploaded_by': doc.get('uploaded_by_name', 'Unknown'),
                    'is_processed': doc.get('is_processed', False),
                    'is_template': doc.get('is_template', False),
                    'created_at': doc['created_at']
                }
                for doc in documents
            ]
        })
    
    @app.route('/api/documents', methods=['POST'])
    @admin_required
    def upload_document():
        try:
            print("Upload document request received")
            
            if 'file' not in request.files:
                return jsonify({'error': 'Fayl seçilməyib'}), 400
            
            file = request.files['file']
            if not file.filename:
                return jsonify({'error': 'Fayl seçin'}), 400
            
            print(f"File received: {file.filename}")
            
            # Get document type from request
            doc_type = request.form.get('document_type', 'other')
            is_template = request.form.get('is_template', 'false').lower() == 'true'
            
            print(f"Document type: {doc_type}, Is template: {is_template}")
            
            # Save file
            import uuid
            from werkzeug.utils import secure_filename
            
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            file_path = os.path.join('documents', unique_filename)
            
            os.makedirs('documents', exist_ok=True)
            file.save(file_path)
            print(f"File saved to: {file_path}")
            
            if not os.path.exists(file_path):
                return jsonify({'error': 'Fayl saxlanmadı'}), 500
            
            # Get file info
            file_size = os.path.getsize(file_path)
            file_type = os.path.splitext(filename)[1].upper().replace('.', '')
            
            print(f"File size: {file_size}, File type: {file_type}")
            
            # Save to database
            try:
                doc_id = db_manager.execute_query(
                    """INSERT INTO documents 
                       (filename, original_name, file_path, file_size, file_type, 
                        uploaded_by, document_type, is_template, is_processed) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (unique_filename, filename, file_path, file_size, file_type, 
                     session['user_id'], doc_type, is_template, False)
                )
                print(f"Document saved to database with ID: {doc_id}")
            except Exception as db_error:
                print(f"Database error: {db_error}")
                if os.path.exists(file_path):
                    os.remove(file_path)
                return jsonify({'error': f'Database xətası: {str(db_error)}'}), 500
            
            # Process with RAG
            try:
                success = rag_service.process_document(file_path, doc_id)
                if success:
                    db_manager.update_document_processed(doc_id, True)
                    print("Document processed successfully")
                else:
                    print("Document processing failed")
            except Exception as process_error:
                print(f"Processing error: {process_error}")
                success = False
            
            return jsonify({
                'message': f'{file_type} faylı yükləndi və işləndi' if success else f'{file_type} faylı yükləndi amma işlənmədi',
                'document': {
                    'id': doc_id,
                    'name': filename,
                    'type': file_type,
                    'document_type': doc_type,
                    'size': file_size,
                    'is_processed': success,
                    'is_template': is_template
                }
            }), 201
            
        except Exception as e:
            print(f"Upload error: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Yükləmə xətası: {str(e)}'}), 500
    
    @app.route('/api/documents/<int:doc_id>/download', methods=['GET'])
    @login_required
    def download_document(doc_id):
        """Download document file with proper cache handling"""
        try:
            print(f"Download request for document ID: {doc_id}")
            
            documents = db_manager.get_documents()
            doc = next((d for d in documents if d['id'] == doc_id), None)
            
            if not doc:
                return jsonify({'error': 'Sənəd tapılmadı'}), 404
            
            if not os.path.exists(doc['file_path']):
                return jsonify({'error': 'Fayl tapılmadı'}), 404
            
            file_size = os.path.getsize(doc['file_path'])
            
            # MIME type mapping
            file_extension = os.path.splitext(doc['original_name'])[1].lower()
            mime_types = {
                '.pdf': 'application/pdf',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.txt': 'text/plain; charset=utf-8',
                '.md': 'text/markdown; charset=utf-8',
                '.json': 'application/json',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.xls': 'application/vnd.ms-excel'
            }
            mimetype = mime_types.get(file_extension, 'application/octet-stream')
            
            def generate():
                with open(doc['file_path'], 'rb') as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        yield chunk
            
            response = Response(
                generate(),
                mimetype=mimetype,
                headers={
                    'Content-Disposition': f'attachment; filename="{doc["original_name"]}"',
                    'Content-Length': str(file_size),
                    'Content-Type': mimetype,
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0',
                    'Accept-Ranges': 'bytes'
                }
            )
            
            print(f"Sending file: {doc['original_name']} ({file_size} bytes)")
            return response
            
        except Exception as e:
            print(f"Download error: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Yükləmə xətası: {str(e)}'}), 500
    
    @app.route('/api/documents/<int:doc_id>', methods=['DELETE'])
    @admin_required
    def delete_document(doc_id):
        doc = db_manager.delete_document(doc_id)
        if not doc:
            return jsonify({'error': 'Sənəd tapılmadı'}), 404
        
        # Delete file
        if os.path.exists(doc['file_path']):
            os.remove(doc['file_path'])
        
        # Delete vector store
        rag_service.delete_document_vectors(doc_id)
        
        return jsonify({'message': 'Sənəd silindi'})
    
    @app.route('/api/documents/<int:doc_id>/reprocess', methods=['POST'])
    @admin_required
    def reprocess_document(doc_id):
        """Reprocess document with enhanced keyword extraction"""
        try:
            print(f"Reprocess request for document ID: {doc_id}")
            
            # Get document info
            documents = db_manager.get_documents()
            doc = next((d for d in documents if d['id'] == doc_id), None)
            
            if not doc:
                return jsonify({'error': 'Sənəd tapılmadı'}), 404
            
            if not os.path.exists(doc['file_path']):
                return jsonify({'error': 'Fayl tapılmadı'}), 404
            
            print(f"Reprocessing document: {doc['original_name']}")
            
            # Delete old vector store
            rag_service.delete_document_vectors(doc_id)
            
            # Mark as not processed
            db_manager.execute_query(
                "UPDATE documents SET is_processed = FALSE WHERE id = ?",
                (doc_id,)
            )
            
            # Reprocess with enhanced keyword extraction
            success = rag_service.process_document(doc['file_path'], doc_id)
            
            if success:
                db_manager.update_document_processed(doc_id, True)
                
                # Get extracted keywords
                keywords_result = db_manager.execute_query(
                    "SELECT keywords FROM documents WHERE id = ?",
                    (doc_id,),
                    fetch_one=True
                )
                
                keywords = []
                if keywords_result:
                    try:
                        keywords_dict = dict(keywords_result)
                        keywords = json.loads(keywords_dict.get('keywords', '[]'))
                    except:
                        keywords = []
                
                return jsonify({
                    'message': 'Sənəd uğurla yenidən işləndi',
                    'document': {
                        'id': doc_id,
                        'name': doc['original_name'],
                        'keywords_count': len(keywords),
                        'top_keywords': keywords[:10] if keywords else []
                    }
                })
            else:
                return jsonify({'error': 'Sənəd işlənmədi'}), 500
                
        except Exception as e:
            print(f"Reprocess error: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Reprocess xətası: {str(e)}'}), 500
    
    @app.route('/api/documents/<int:doc_id>/keywords', methods=['GET'])
    @login_required
    def get_document_keywords(doc_id):
        """Get document keywords"""
        try:
            # Get document info
            result = db_manager.execute_query(
                "SELECT original_name, keywords FROM documents WHERE id = ?",
                (doc_id,),
                fetch_one=True
            )
            
            if not result:
                return jsonify({'error': 'Sənəd tapılmadı'}), 404
            
            doc_dict = dict(result)
            keywords = []
            
            try:
                keywords = json.loads(doc_dict.get('keywords', '[]'))
            except:
                keywords = []
            
            return jsonify({
                'document_id': doc_id,
                'document_name': doc_dict['original_name'],
                'keywords': keywords,
                'keywords_count': len(keywords)
            })
            
        except Exception as e:
            return jsonify({'error': f'Keywords xətası: {str(e)}'}), 500
    
    @app.route('/api/admin/documents/bulk-reprocess', methods=['POST'])
    @admin_required
    def bulk_reprocess_documents():
        """Reprocess multiple documents"""
        try:
            data = request.get_json()
            document_ids = data.get('document_ids', [])
            
            if not document_ids:
                # Reprocess all documents
                documents = db_manager.get_documents()
                document_ids = [doc['id'] for doc in documents]
            
            results = {
                'success': [],
                'failed': []
            }
            
            for doc_id in document_ids:
                try:
                    # Get document
                    doc_result = db_manager.execute_query(
                        "SELECT * FROM documents WHERE id = ?",
                        (doc_id,),
                        fetch_one=True
                    )
                    
                    if not doc_result:
                        results['failed'].append({
                            'id': doc_id,
                            'error': 'Sənəd tapılmadı'
                        })
                        continue
                    
                    doc = dict(doc_result)
                    
                    # Delete old vectors
                    rag_service.delete_document_vectors(doc_id)
                    
                    # Reprocess
                    success = rag_service.process_document(doc['file_path'], doc_id)
                    
                    if success:
                        db_manager.update_document_processed(doc_id, True)
                        results['success'].append({
                            'id': doc_id,
                            'name': doc['original_name']
                        })
                    else:
                        results['failed'].append({
                            'id': doc_id,
                            'name': doc['original_name'],
                            'error': 'İşlənmədi'
                        })
                        
                except Exception as e:
                    results['failed'].append({
                        'id': doc_id,
                        'error': str(e)
                    })
            
            return jsonify({
                'message': f"{len(results['success'])} sənəd uğurla işləndi, {len(results['failed'])} uğursuz",
                'results': results
            })
            
        except Exception as e:
            return jsonify({'error': f'Bulk reprocess xətası: {str(e)}'}), 500
    
    @app.route('/api/documents/templates', methods=['GET'])
    @login_required
    def list_template_documents():
        """List all template documents"""
        try:
            templates = db_manager.execute_query(
                """SELECT d.*, u.username as uploaded_by_name 
                   FROM documents d 
                   JOIN users u ON d.uploaded_by = u.id 
                   WHERE d.is_template = TRUE 
                   ORDER BY d.document_type, d.created_at DESC"""
            )
            
            return jsonify({
                'templates': [
                    {
                        'id': doc['id'],
                        'name': doc['original_name'],
                        'type': doc['file_type'],
                        'document_type': doc.get('document_type', 'other'),
                        'size': doc['file_size'],
                        'uploaded_by': doc['uploaded_by_name'],
                        'created_at': doc['created_at'],
                        'download_url': f"/api/documents/{doc['id']}/download"
                    }
                    for doc in templates
                ]
            })
            
        except Exception as e:
            return jsonify({'error': f'Templates xətası: {str(e)}'}), 500
    
    @app.route('/api/documents/search-by-keywords', methods=['POST'])
    @login_required
    def search_documents_by_keywords():
        """Search documents by keywords"""
        try:
            data = request.get_json()
            search_keywords = data.get('keywords', [])
            
            if not search_keywords:
                return jsonify({'error': 'Açar sözlər tələb olunur'}), 400
            
            documents = db_manager.get_documents()
            results = []
            
            for doc in documents:
                if not doc.get('keywords'):
                    continue
                
                try:
                    doc_keywords = json.loads(doc['keywords'])
                    
                    # Calculate relevance score
                    score = 0
                    matched_keywords = []
                    
                    for search_kw in search_keywords:
                        search_kw_lower = search_kw.lower()
                        for doc_kw in doc_keywords:
                            doc_kw_lower = doc_kw.lower()
                            if search_kw_lower in doc_kw_lower or doc_kw_lower in search_kw_lower:
                                score += 1
                                if doc_kw not in matched_keywords:
                                    matched_keywords.append(doc_kw)
                    
                    if score > 0:
                        results.append({
                            'document': {
                                'id': doc['id'],
                                'name': doc['original_name'],
                                'type': doc.get('document_type', 'other')
                            },
                            'relevance_score': score,
                            'matched_keywords': matched_keywords[:10]
                        })
                        
                except:
                    continue
            
            # Sort by relevance
            results.sort(key=lambda x: x['relevance_score'], reverse=True)
            
            return jsonify({
                'search_keywords': search_keywords,
                'results': results[:20],
                'total_results': len(results)
            })
            
        except Exception as e:
            return jsonify({'error': f'Search xətası: {str(e)}'}), 500
        

    # Add these endpoints to simple_app.py after other document routes

    @app.route('/api/documents/<int:doc_id>/keywords', methods=['PUT'])
    @admin_required
    def update_document_keywords(doc_id):
        """Admin can manually update document keywords"""
        try:
            data = request.get_json()
            new_keywords = data.get('keywords', [])
            
            # Validate keywords
            if not isinstance(new_keywords, list):
                return jsonify({'error': 'Açar sözlər list formatında olmalıdır'}), 400
            
            # Limit to 15 keywords
            if len(new_keywords) > 15:
                return jsonify({'error': 'Maksimum 15 açar söz əlavə edilə bilər'}), 400
            
            # Clean and validate each keyword
            cleaned_keywords = []
            for keyword in new_keywords:
                keyword = str(keyword).strip()
                if keyword and len(keyword) >= 2 and len(keyword) <= 50:
                    cleaned_keywords.append(keyword)
            
            # Check document exists
            doc_result = db_manager.execute_query(
                "SELECT original_name FROM documents WHERE id = ?",
                (doc_id,),
                fetch_one=True
            )
            
            if not doc_result:
                return jsonify({'error': 'Sənəd tapılmadı'}), 404
            
            doc_name = dict(doc_result)['original_name']
            
            # Update keywords in database
            keywords_json = json.dumps(cleaned_keywords, ensure_ascii=False)
            db_manager.execute_query(
                "UPDATE documents SET keywords = ? WHERE id = ?",
                (keywords_json, doc_id)
            )
            
            print(f"Keywords updated for document {doc_id}: {cleaned_keywords}")
            
            return jsonify({
                'message': 'Açar sözlər yeniləndi',
                'document_id': doc_id,
                'document_name': doc_name,
                'keywords': cleaned_keywords,
                'keywords_count': len(cleaned_keywords)
            })
            
        except Exception as e:
            print(f"Update keywords error: {e}")
            return jsonify({'error': f'Açar sözlər yenilənmədi: {str(e)}'}), 500
    
    @app.route('/api/documents/<int:doc_id>/add-keywords', methods=['POST'])
    @admin_required
    def add_document_keywords(doc_id):
        """Admin can add additional keywords to existing ones"""
        try:
            data = request.get_json()
            additional_keywords = data.get('keywords', [])
            
            if not isinstance(additional_keywords, list):
                return jsonify({'error': 'Açar sözlər list formatında olmalıdır'}), 400
            
            # Get existing keywords
            result = db_manager.execute_query(
                "SELECT keywords, original_name FROM documents WHERE id = ?",
                (doc_id,),
                fetch_one=True
            )
            
            if not result:
                return jsonify({'error': 'Sənəd tapılmadı'}), 404
            
            doc_dict = dict(result)
            existing_keywords = []
            
            try:
                if doc_dict.get('keywords'):
                    existing_keywords = json.loads(doc_dict['keywords'])
            except:
                existing_keywords = []
            
            # Combine keywords
            all_keywords = existing_keywords + additional_keywords
            
            # Remove duplicates and limit to 15
            unique_keywords = []
            seen = set()
            for keyword in all_keywords:
                keyword = str(keyword).strip().lower()
                if keyword and keyword not in seen and len(keyword) >= 2 and len(keyword) <= 50:
                    seen.add(keyword)
                    unique_keywords.append(keyword)
            
            unique_keywords = unique_keywords[:15]  # Limit to 15
            
            # Update in database
            keywords_json = json.dumps(unique_keywords, ensure_ascii=False)
            db_manager.execute_query(
                "UPDATE documents SET keywords = ? WHERE id = ?",
                (keywords_json, doc_id)
            )
            
            return jsonify({
                'message': 'Açar sözlər əlavə edildi',
                'document_id': doc_id,
                'document_name': doc_dict['original_name'],
                'keywords': unique_keywords,
                'keywords_count': len(unique_keywords),
                'added_count': len(unique_keywords) - len(existing_keywords)
            })
            
        except Exception as e:
            print(f"Add keywords error: {e}")
            return jsonify({'error': f'Açar sözlər əlavə edilmədi: {str(e)}'}), 500
    
    @app.route('/api/documents/<int:doc_id>/remove-keyword', methods=['DELETE'])
    @admin_required
    def remove_document_keyword(doc_id):
        """Admin can remove a specific keyword"""
        try:
            data = request.get_json()
            keyword_to_remove = data.get('keyword', '').strip().lower()
            
            if not keyword_to_remove:
                return jsonify({'error': 'Silinəcək açar söz təyin edilməyib'}), 400
            
            # Get existing keywords
            result = db_manager.execute_query(
                "SELECT keywords, original_name FROM documents WHERE id = ?",
                (doc_id,),
                fetch_one=True
            )
            
            if not result:
                return jsonify({'error': 'Sənəd tapılmadı'}), 404
            
            doc_dict = dict(result)
            existing_keywords = []
            
            try:
                if doc_dict.get('keywords'):
                    existing_keywords = json.loads(doc_dict['keywords'])
            except:
                existing_keywords = []
            
            # Remove the keyword
            updated_keywords = [kw for kw in existing_keywords if kw.lower() != keyword_to_remove]
            
            if len(updated_keywords) == len(existing_keywords):
                return jsonify({'error': 'Bu açar söz tapılmadı'}), 404
            
            # Update in database
            keywords_json = json.dumps(updated_keywords, ensure_ascii=False)
            db_manager.execute_query(
                "UPDATE documents SET keywords = ? WHERE id = ?",
                (keywords_json, doc_id)
            )
            
            return jsonify({
                'message': f'"{keyword_to_remove}" açar sözü silindi',
                'document_id': doc_id,
                'document_name': doc_dict['original_name'],
                'keywords': updated_keywords,
                'keywords_count': len(updated_keywords)
            })
            
        except Exception as e:
            print(f"Remove keyword error: {e}")
            return jsonify({'error': f'Açar söz silinmədi: {str(e)}'}), 500
    
    # Override the upload endpoint to include manual keywords
    @app.route('/api/documents/upload-with-keywords', methods=['POST'])
    @admin_required
    def upload_document_with_keywords():
        """Upload document with manual keywords"""
        try:
            if 'file' not in request.files:
                return jsonify({'error': 'Fayl seçilməyib'}), 400
            
            file = request.files['file']
            if not file.filename:
                return jsonify({'error': 'Fayl seçin'}), 400
            
            # Get parameters
            doc_type = request.form.get('document_type', 'other')
            is_template = request.form.get('is_template', 'false').lower() == 'true'
            manual_keywords = request.form.get('keywords', '')
            
            # Parse manual keywords
            keywords_list = []
            if manual_keywords:
                try:
                    # Try to parse as JSON first
                    keywords_list = json.loads(manual_keywords)
                except:
                    # If not JSON, split by comma
                    keywords_list = [kw.strip() for kw in manual_keywords.split(',') if kw.strip()]
            
            # Limit to 15 keywords
            keywords_list = keywords_list[:15]
            
            print(f"Uploading file with manual keywords: {keywords_list}")
            
            # Save file
            import uuid
            from werkzeug.utils import secure_filename
            
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            file_path = os.path.join('documents', unique_filename)
            
            os.makedirs('documents', exist_ok=True)
            file.save(file_path)
            
            # Get file info
            file_size = os.path.getsize(file_path)
            file_type = os.path.splitext(filename)[1].upper().replace('.', '')
            
            # Save to database with initial keywords
            doc_id = db_manager.execute_query(
                """INSERT INTO documents 
                   (filename, original_name, file_path, file_size, file_type, 
                    uploaded_by, document_type, is_template, is_processed, keywords) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (unique_filename, filename, file_path, file_size, file_type, 
                 session['user_id'], doc_type, is_template, False, 
                 json.dumps(keywords_list, ensure_ascii=False) if keywords_list else None)
            )
            
            # Process with RAG
            try:
                success = rag_service.process_document(file_path, doc_id)
                if success:
                    db_manager.update_document_processed(doc_id, True)
                    
                    # If manual keywords were provided, merge with extracted ones
                    if keywords_list:
                        # Get extracted keywords
                        result = db_manager.execute_query(
                            "SELECT keywords FROM documents WHERE id = ?",
                            (doc_id,),
                            fetch_one=True
                        )
                        
                        extracted_keywords = []
                        if result:
                            try:
                                extracted_keywords = json.loads(dict(result).get('keywords', '[]'))
                            except:
                                extracted_keywords = []
                        
                        # Merge and deduplicate
                        all_keywords = list(set(keywords_list + extracted_keywords))[:15]
                        
                        # Update with merged keywords
                        db_manager.execute_query(
                            "UPDATE documents SET keywords = ? WHERE id = ?",
                            (json.dumps(all_keywords, ensure_ascii=False), doc_id)
                        )
                        
                        keywords_list = all_keywords
                
            except Exception as process_error:
                print(f"Processing error: {process_error}")
                success = False
            
            return jsonify({
                'message': f'{file_type} faylı yükləndi və işləndi',
                'document': {
                    'id': doc_id,
                    'name': filename,
                    'type': file_type,
                    'document_type': doc_type,
                    'size': file_size,
                    'is_processed': success,
                    'is_template': is_template,
                    'keywords': keywords_list
                }
            }), 201
            
        except Exception as e:
            print(f"Upload error: {e}")
            return jsonify({'error': f'Yükləmə xətası: {str(e)}'}), 500
    
    # ============= CONVERSATION ROUTES =============
    @app.route('/api/chat/conversations', methods=['GET'])
    @login_required
    def list_conversations():
        conversations = db_manager.get_conversations(session['user_id'])
        
        return jsonify({
            'conversations': [
                {
                    'id': conv['id'],
                    'title': conv['title'],
                    'document_id': conv['document_id'],
                    'document_name': conv.get('document_name'),
                    'message_count': len(json.loads(conv['messages'])),
                    'created_at': conv['created_at'],
                    'updated_at': conv['updated_at']
                }
                for conv in conversations
            ]
        })
    
    @app.route('/api/chat/conversations/<int:conv_id>', methods=['GET'])
    @login_required  
    def get_conversation(conv_id):
        conversation = db_manager.get_conversation(conv_id, session['user_id'])
        
        if not conversation:
            return jsonify({'error': 'Söhbət tapılmadı'}), 404
        
        return jsonify({
            'conversation': {
                'id': conversation['id'],
                'title': conversation['title'],
                'document_id': conversation['document_id'],
                'messages': json.loads(conversation['messages']),
                'created_at': conversation['created_at'],
                'updated_at': conversation['updated_at']
            }
        })
    
    @app.route('/api/chat/conversations/<int:conv_id>/rename', methods=['PUT'])
    @login_required
    def rename_conversation(conv_id):
        data = request.get_json()
        new_title = data.get('title', '').strip()
        
        if not new_title:
            return jsonify({'error': 'Yeni başlıq tələb olunur'}), 400
        
        conversation = db_manager.get_conversation(conv_id, session['user_id'])
        if not conversation:
            return jsonify({'error': 'Söhbət tapılmadı'}), 404
        
        db_manager.execute_query(
            "UPDATE conversations SET title = ? WHERE id = ? AND user_id = ?",
            (new_title, conv_id, session['user_id'])
        )
        
        return jsonify({'message': 'Başlıq dəyişdirildi'})
    
    @app.route('/api/chat/conversations/<int:conv_id>', methods=['DELETE'])
    @login_required
    def delete_conversation(conv_id):
        success = db_manager.delete_conversation(conv_id, session['user_id'])
        if success:
            return jsonify({'message': 'Söhbət silindi'})
        return jsonify({'error': 'Söhbət tapılmadı'}), 404
    
    # ============= TEMPLATE MANAGEMENT ROUTES =============
    @app.route('/api/templates/initialize', methods=['POST'])
    @admin_required
    def initialize_templates():
        """Initialize template documents from example_docs folder"""
        try:
            example_docs_path = os.path.join(os.path.dirname(__file__), 'example_docs')
            
            if not os.path.exists(example_docs_path):
                return jsonify({'error': 'example_docs klasörü tapılmadı'}), 404
            
            # Template type mapping based on filename
            template_mappings = {
                'ezamiyyet_template.docx': 'business_trip',
                'memorandum_template.docx': 'memorandum',
                'mezuniyyet_template.docx': 'vacation',
                'muqavile_template.docx': 'contract',
                'telefon_kitabcasi.docx': 'phone_book'
            }
            
            initialized_count = 0
            errors = []
            
            for filename, doc_type in template_mappings.items():
                file_path = os.path.join(example_docs_path, filename)
                
                if not os.path.exists(file_path):
                    errors.append(f"{filename} faylı tapılmadı")
                    continue
                
                # Check if template already exists
                existing = db_manager.execute_query(
                    "SELECT id FROM documents WHERE original_name = ? AND is_template = TRUE",
                    (filename,), fetch_one=True
                )
                
                if existing:
                    print(f"Template {filename} already exists, skipping...")
                    continue
                
                try:
                    # Copy file to documents directory
                    import uuid
                    import shutil
                    
                    unique_filename = f"{uuid.uuid4()}_{filename}"
                    dest_path = os.path.join('documents', unique_filename)
                    
                    os.makedirs('documents', exist_ok=True)
                    shutil.copy2(file_path, dest_path)
                    
                    # Get file info
                    file_size = os.path.getsize(dest_path)
                    file_type = os.path.splitext(filename)[1].upper().replace('.', '')
                    
                    # Save to database as template
                    doc_id = db_manager.execute_query(
                        """INSERT INTO documents 
                           (filename, original_name, file_path, file_size, file_type, 
                            uploaded_by, document_type, is_template, is_processed) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (unique_filename, filename, dest_path, file_size, file_type, 
                         session['user_id'], doc_type, True, False)
                    )
                    
                    # Process with RAG (optional for templates)
                    try:
                        success = rag_service.process_document(dest_path, doc_id)
                        if success:
                            db_manager.update_document_processed(doc_id, True)
                    except Exception as process_error:
                        print(f"Template processing warning for {filename}: {process_error}")
                        # Don't fail initialization if processing fails
                    
                    initialized_count += 1
                    print(f"Initialized template: {filename} with type: {doc_type}")
                    
                except Exception as file_error:
                    errors.append(f"{filename}: {str(file_error)}")
                    continue
            
            message = f"{initialized_count} şablon uğurla yükləndi"
            if errors:
                message += f". Xətalar: {'; '.join(errors)}"
            
            return jsonify({
                'message': message,
                'initialized_count': initialized_count,
                'errors': errors
            })
            
        except Exception as e:
            print(f"Template initialization error: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Şablon yükləmə xətası: {str(e)}'}), 500

    @app.route('/api/templates', methods=['GET'])
    @login_required
    def list_templates():
        """List all available templates"""
        try:
            documents = db_manager.get_documents()
            templates = [
                {
                    'id': doc['id'],
                    'name': doc['original_name'],
                    'type': doc.get('document_type', 'other'),
                    'size': doc['file_size'],
                    'file_type': doc['file_type'],
                    'download_url': f"/api/documents/{doc['id']}/download",
                    'created_at': doc['created_at']
                }
                for doc in documents if doc.get('is_template')
            ]
            
            return jsonify({
                'templates': templates,
                'count': len(templates)
            })
            
        except Exception as e:
            return jsonify({'error': f'Şablon siyahısı alınmadı: {str(e)}'}), 500

    # ============= UTILITY ROUTES =============
    @app.route('/api/documents/types', methods=['GET'])
    def get_document_types():
        """Get available document types"""
        types = [
            {'value': 'contact', 'label': 'Əlaqə məlumatları'},
            {'value': 'contract', 'label': 'Müqavilə'},
            {'value': 'vacation', 'label': 'Məzuniyyət'},
            {'value': 'business_trip', 'label': 'Ezamiyyət'},
            {'value': 'memorandum', 'label': 'Anlaşma memorandumu'},
            {'value': 'report', 'label': 'Hesabat'},
            {'value': 'letter', 'label': 'Məktub'},
            {'value': 'invoice', 'label': 'Qaimə'},
            {'value': 'other', 'label': 'Digər'}
        ]
        return jsonify({'types': types})
    
    # ============= DEBUG ROUTES =============
    @app.route('/api/debug/contact-search/<int:doc_id>/<path:query>', methods=['GET'])
    @login_required
    def debug_contact_search(doc_id, query):
        """Debug endpoint to test contact search strategies"""
        from services.enhanced_contact_search import EnhancedContactSearcher
        
        try:
            searcher = EnhancedContactSearcher(rag_service)
            result = searcher.search_contact_with_fallback(query, doc_id)
            
            return jsonify({
                'query': query,
                'document_id': doc_id,
                'result': result,
                'debug': True
            })
            
        except Exception as e:
            return jsonify({
                'error': str(e),
                'query': query,
                'document_id': doc_id
            })
    
    @app.route('/api/debug/answer-quality/<int:doc_id>/<path:query>', methods=['GET'])
    @login_required
    def debug_answer_quality(doc_id, query):
        """Test answer generation quality"""
        try:
            # Get document info
            doc_info = db_manager.execute_query(
                "SELECT original_name, document_type FROM documents WHERE id = ?",
                (doc_id,), fetch_one=True
            )
            
            if not doc_info:
                return jsonify({'error': 'Document not found'})
            
            doc_dict = dict(doc_info)
            
            # Get context
            context = rag_service.search_relevant_content(query, doc_id)
            if not context:
                return jsonify({'error': 'No context found'})
            
            # Generate answer
            result = rag_service.answer_question(query, doc_id)
            
            return jsonify({
                'query': query,
                'document': {
                    'id': doc_id,
                    'name': doc_dict['original_name'],
                    'type': doc_dict.get('document_type', 'unknown')
                },
                'answer': result.get('answer', ''),
                'context_preview': context[:300] + "..." if len(context) > 300 else context,
                'debug': True
            })
            
        except Exception as e:
            import traceback
            return jsonify({
                'error': str(e),
                'traceback': traceback.format_exc(),
                'query': query,
                'document_id': doc_id
            })
    
    @app.route('/api/debug/session', methods=['GET'])
    def debug_session():
        return jsonify({
            'session_data': dict(session),
            'has_user_id': 'user_id' in session,
            'cookies': dict(request.cookies),
            'headers': dict(request.headers)
        })
    
    # ============= HEALTH CHECK ROUTES =============
    @app.route('/api/health', methods=['GET'])
    def health_check():
        return jsonify({
            'status': 'healthy',
            'session_exists': bool(session),
            'authenticated': 'user_id' in session,
            'features': [
                'context_aware_chat',
                'improved_document_matching', 
                'structured_formatting',
                'conversation_memory',
                'keyword_extraction',
                'document_reprocessing'
            ]
        })
    
    @app.route('/')
    def index():
        return jsonify({
            'message': 'Enhanced RAG Backend Server with Context Awareness',
            'status': 'running',
            'version': '2.0',
            'features': [
                'Context-aware conversations',
                'Improved document matching',
                'Structured answer formatting',
                'Conversation memory',
                'Enhanced contact queries',
                'Keyword extraction and search',
                'Document reprocessing'
            ],
            'frontend_url': 'http://localhost:3000',
            'api_endpoints': {
                'health': '/api/health',
                'auth_check': '/api/auth/check',
                'documents': '/api/documents',
                'document_types': '/api/documents/types',
                'chat': '/api/chat/ask',
                'reprocess': '/api/documents/{id}/reprocess',
                'bulk_reprocess': '/api/admin/documents/bulk-reprocess',
                'keywords': '/api/documents/{id}/keywords'
            }
        })
    
    @app.route('/api')
    def api_root():
        return jsonify({
            'message': 'Enhanced RAG API v2.0',
            'status': 'active',
            'features': [
                'Context awareness',
                'Memory persistence',
                'Structured formatting',
                'Keyword extraction',
                'Document reprocessing'
            ],
            'endpoints': [
                '/api/auth/login',
                '/api/auth/check', 
                '/api/documents',
                '/api/documents/types',
                '/api/chat/ask',
                '/api/health',
                '/api/documents/{id}/reprocess'
            ]
        })
    
    return app

if __name__ == '__main__':
    app = create_simple_app()
    
    print("🚀 Enhanced RAG Backend Starting...")
    print("=" * 60)
    print("🌐 Server: http://localhost:5000")
    print("👤 Default: admin / admin123")
    print("🧠 Context-Aware Chat: ENABLED")
    print("🔍 Improved Document Matching: ENABLED") 
    print("📋 Structured Answer Formatting: ENABLED")
    print("💾 Conversation Memory: ENABLED")
    print("🔑 Keyword Extraction: ENABLED")
    print("♻️ Document Reprocessing: ENABLED")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)