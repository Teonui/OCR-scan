from mem0 import Memory
import os

class AntigravityMemory:
    def __init__(self):
        # Khởi tạo Mem0 (Mặc định dùng OpenAI API Key từ os.environ)
        self.memory = Memory()
        self.user_id = "researcher_01" # Định danh duy nhất cho bạn

    def get_context(self, user_query):
        """Truy xuất ký ức liên quan trước khi gửi cho AI"""
        memories = self.memory.search(user_query, user_id=self.user_id)
        # Chuyển danh sách ký ức thành chuỗi để đưa vào Prompt
        context = "\n".join([m['text'] for m in memories])
        return context

    def save_insight(self, user_input, ai_response):
        """Lưu lại thông tin quan trọng sau cuộc hội thoại"""
        # Bạn có thể lưu câu hỏi của mình hoặc tóm tắt ngắn gọn
        data_to_save = f"User asked: {user_input}. Insight: {ai_response[:100]}..."
        self.memory.add(data_to_save, user_id=self.user_id)

# Khởi tạo instance để dùng chung trong dự án
mem_manager = AntigravityMemory()
