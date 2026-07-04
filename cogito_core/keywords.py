"""
中文关键词抽取 —— 移植自白龙马 memory/keywords.js（MIT）

jieba 分词优先，n-gram 兜底。jieba 已列入 requirements.txt。
"""

from collections import Counter

try:
    import jieba
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False

STOP_WORDS_CN = {
    '的', '了', '是', '在', '我', '你', '他', '她', '它',
    '我们', '你们', '他们', '这', '那', '有', '没有',
    '和', '与', '把', '被', '因为', '所以', '如果',
    '一个', '一些', '什么', '怎么', '为什么',
    '帮我', '请', '好的', '明白', '告诉', '让', '做', '去', '来', '说', '给',
    '今天', '昨天', '前天', '大前天',
    '今早', '今晨', '今夜', '今晚', '昨晚', '昨夜', '昨日', '今日',
}

# 英文停用词 —— 工具对话中高频出现但不携带主题信息的英文词
STOP_WORDS_EN = frozenset({
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'can', 'could', 'may', 'might', 'shall', 'should', 'must',
    'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him',
    'her', 'us', 'them', 'my', 'your', 'his', 'its', 'our',
    'their', 'mine', 'yours', 'hers', 'ours', 'theirs',
    'this', 'that', 'these', 'those', 'here', 'there',
    'what', 'which', 'who', 'whom', 'when', 'where', 'why', 'how',
    'all', 'both', 'each', 'every', 'few', 'more', 'most',
    'other', 'some', 'such', 'no', 'nor', 'not', 'only',
    'own', 'same', 'so', 'than', 'too', 'very', 'just',
    'and', 'but', 'or', 'if', 'because', 'as', 'until',
    'while', 'of', 'at', 'by', 'for', 'with', 'about',
    'between', 'into', 'through', 'during', 'before', 'after',
    'above', 'below', 'to', 'from', 'in', 'out', 'on', 'off',
    'over', 'under', 'again', 'further', 'then', 'once',
    'also', 'any', 'each', 'even', 'ever', 'now', 'still',
    'yet', 'already', 'always', 'never', 'often', 'really',
    'very', 'much', 'many', 'well', 'back', 'down', 'up',
    'name', 'task', 'skill',  # 工具对话高频噪音词
})

# 向后兼容别名
STOP_WORDS = STOP_WORDS_CN

# 高频 2字噪声 n-gram —— 在几乎任何上下文中都不携带主题信息。
# 这是 n-gram 抽取最常被挤占 top-3 的元凶。
STOP_NOISE_BIGRAMS = {
    '这是', '这个', '那个', '哪些', '哪个', '什么', '怎么', '如何',
    '在哪', '没有', '可以', '一个', '一些', '时候', '不是', '就是',
    '还有', '然后', '而且', '或者', '如果', '因为', '所以', '但是',
    '就是', '还是', '可是', '什么', '那样', '这样', '那么', '那么',
    '现在', '刚才', '已经', '还是', '应该', '可能', '需要', '能够',
    '只要', '难道', '有点', '有点', '是吗', '行了', '好的', '没事',
    '是的', '还是', '那个', '哪些', '哪个', '别的', '任何', '所有',
    '都是', '都是', '是对', '不能', '不会', '还没', '要去', '还要',
    '刚才', '一起', '新开', '然后',
}

STOP_CHARS = set('的了着过来去吗呢吧啊呀嘛哦和与跟或及并很太再又也都还只就才')

STOP_HEAD_CHARS = set('们个些点次件种样')
STOP_TAIL_CHARS = set('一几某每这那今')


def _is_valid_ngram(word: str) -> bool:
    if not word or len(word) < 2 or word in STOP_WORDS:
        return False
    if word.lower() in STOP_WORDS_EN:
        return False
    if len(word) == 2 and word in STOP_NOISE_BIGRAMS:
        return False
    for ch in word:
        if ch in STOP_CHARS:
            return False
    if word[0] in STOP_HEAD_CHARS:
        return False
    if word[-1] in STOP_TAIL_CHARS:
        return False
    if len(word) > 2 and len(set(word)) < len(word) and not word.isascii():
        # 纯中文重复字符（"哈哈哈"）→ 过滤；英文 "hook"/"look" 等不在此列
        return False
    return True


def _length_weight(n: int) -> float:
    """焦点栈场景：长词 > 短词。3-4字词更有语义价值。"""
    if n == 2:
        return 0.6
    if n == 3:
        return 1.5
    if n == 4:
        return 2.0
    return 1.0


def _extract_ngram(text: str, max_keywords: int = 8) -> list[str]:
    """字符 n-gram 兜底提取（jieba 不可用时）。"""
    import re
    freq = Counter()

    chinese = re.sub(r'[a-zA-Z]+', ' ', text)
    for i in range(len(chinese) - 1):
        for ngram_len in range(2, min(5, len(chinese) - i + 1)):
            word = chinese[i:i + ngram_len].strip()
            if word and _is_valid_ngram(word):
                freq[word] += 1

    english_words = re.findall(r'[a-zA-Z]{3,}', text)
    for w in english_words:
        wl = w.lower()
        if wl not in STOP_WORDS_EN:
            freq[w] += 2

    scored = [(w, f * _length_weight(len(w))) for w, f in freq.items()]
    scored.sort(key=lambda x: (-x[1], -len(x[0])))
    return [w for w, _ in scored[:max_keywords]]


def _extract_jieba(text: str, max_keywords: int = 8) -> list[str]:
    """jieba 分词提取（主路径）。"""
    import re
    cleaned = re.sub(r'[，。！？、；：""''【】［］（）0-9]', ' ', text)
    cleaned = re.sub(r'\\s+', ' ', cleaned).strip()
    if not cleaned:
        return []

    words = [w.strip() for w in jieba.cut(cleaned) if w.strip()]
    freq = Counter()

    for w in words:
        if not _is_valid_ngram(w):
            continue
        freq[w] += 1

    # 英文词
    english = re.findall(r'[a-zA-Z]{3,}', text)
    for w in english:
        wl = w.lower()
        if wl not in STOP_WORDS_EN:
            freq[w] += 2

    scored = [(w, f * _length_weight(len(w))) for w, f in freq.items()]
    scored.sort(key=lambda x: (-x[1], -len(x[0])))
    return [w for w, _ in scored[:max_keywords]]


def extract_keywords(text: str, max_keywords: int = 8) -> list[str]:
    """从中文文本中提取关键词。

    jieba 分词优先（requirements.txt 已声明），不可用时 n-gram 兜底。

    Args:
        text: 输入文本
        max_keywords: 最多返回多少个关键词

    Returns:
        按 (词频×长度权重) 降序排列的关键词列表
    """
    if not text:
        return []

    if _HAS_JIEBA:
        return _extract_jieba(text, max_keywords)
    return _extract_ngram(text, max_keywords)
