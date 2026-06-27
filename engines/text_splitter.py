# -*- coding: utf-8 -*-
import re
from typing import List

def split_vietnamese_text(text: str, max_chars: int = 150) -> List[str]:
    """
    Phân tách văn bản tiếng Việt dài thành các đoạn nhỏ tối ưu (80 - 150 ký tự).
    Giúp tránh tràn VRAM của mô hình TTS và đảm bảo chất lượng giọng đọc tự nhiên.
    """
    if not text or not text.strip():
        return []
        
    # Chuẩn hóa các dấu xuống dòng liên tiếp
    text = re.sub(r'\n+', '\n', text)
    
    # Bước 1: Chia văn bản thành các câu dựa trên dấu chấm câu lớn (. ? ! ; \n)
    # Dùng regex lookbehind để giữ lại các dấu chấm câu này ở cuối mỗi phần tử tách ra
    raw_sentences = re.split(r'(?<=[.?!;\n])', text)
    
    sentences = []
    for s in raw_sentences:
        s = s.strip()
        if not s:
            continue
        sentences.append(s)
        
    # Bước 2: Với các câu dài vượt quá max_chars, tiếp tục chia nhỏ tại dấu phẩy hoặc khoảng trắng
    final_sentences = []
    for s in sentences:
        if len(s) <= max_chars:
            final_sentences.append(s)
        else:
            sub_parts = split_long_sentence(s, max_chars)
            final_sentences.extend(sub_parts)
            
    # Bước 3: Gộp các câu ngắn (nhỏ hơn 40 ký tự) để giảm overhead sinh âm thanh của GPU
    grouped_sentences = []
    current_chunk = ""
    
    for s in final_sentences:
        if not current_chunk:
            current_chunk = s
        elif len(current_chunk) + len(s) + 1 <= max_chars:
            # Nối tiếp nếu tổng độ dài vẫn nằm trong giới hạn an toàn
            current_chunk += " " + s
        else:
            grouped_sentences.append(current_chunk.strip())
            current_chunk = s
            
    if current_chunk:
        grouped_sentences.append(current_chunk.strip())
        
    return grouped_sentences

def split_long_sentence(sentence: str, max_chars: int) -> List[str]:
    """
    Chia nhỏ một câu quá dài bằng cách phân tách ở các dấu phẩy, 
    nếu vẫn quá dài thì chia theo khoảng trắng giữa các từ.
    """
    # Phân tách ở dấu phẩy (và giữ lại dấu phẩy)
    parts = re.split(r'(?<=[,])', sentence)
    sub_sentences = []
    current_part = ""
    
    for p in parts:
        p = p.strip()
        if not p:
            continue
            
        if len(p) <= max_chars:
            if not current_part:
                current_part = p
            elif len(current_part) + len(p) + 1 <= max_chars:
                current_part += " " + p
            else:
                sub_sentences.append(current_part.strip())
                current_part = p
        else:
            # Nếu cụm từ phân tách bởi dấu phẩy vẫn dài hơn max_chars, chia nhỏ theo từ
            if current_part:
                sub_sentences.append(current_part.strip())
                current_part = ""
                
            words = p.split()
            word_chunk = ""
            for w in words:
                if len(word_chunk) + len(w) + 1 <= max_chars:
                    word_chunk += (" " if word_chunk else "") + w
                else:
                    if word_chunk:
                        sub_sentences.append(word_chunk.strip())
                    word_chunk = w
            if word_chunk:
                current_part = word_chunk
                
    if current_part:
        sub_sentences.append(current_part.strip())
        
    return sub_sentences
