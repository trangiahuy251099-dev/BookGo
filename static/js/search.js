// Hàm loại bỏ dấu tiếng Việt
function removeVietnameseTones(str) {
    str = str.toLowerCase();
    str = str.replace(/à|á|ạ|ả|ã|â|ầ|ấ|ậ|ẩ|ẫ|ă|ằ|ắ|ặ|ẳ|ẵ/g, "a");
    str = str.replace(/è|é|ẹ|ẻ|ẽ|ê|ề|ế|ệ|ể|ễ/g, "e");
    str = str.replace(/ì|í|ị|ỉ|ĩ/g, "i");
    str = str.replace(/ò|ó|ọ|ỏ|õ|ô|ồ|ố|ộ|ổ|ỗ|ơ|ờ|ớ|ợ|ở|ỡ/g, "o");
    str = str.replace(/ù|ú|ụ|ủ|ũ|ư|ừ|ứ|ự|ử|ữ/g, "u");
    str = str.replace(/ỳ|ý|ỵ|ỷ|ỹ/g, "y");
    str = str.replace(/đ/g, "d");
    return str;
}

let debounceTimer;
const searchInput = document.getElementById('searchInput');
const suggestDropdown = document.getElementById('suggestDropdown');

if (searchInput) {
    searchInput.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        const keyword = this.value.trim();
        if (keyword.length < 2) {
            suggestDropdown.style.display = 'none';
            return;
        }
        debounceTimer = setTimeout(() => {
            fetch(`/api/search-suggest?q=${encodeURIComponent(keyword)}`)
                .then(response => response.json())
                .then(data => {
                    if (data.suggestions && data.suggestions.length > 0) {
                        let html = '';
                        data.suggestions.forEach(book => {
                            html += `
                                <a href="/book/${book.id}" class="dropdown-item d-flex align-items-center">
                                    <img src="${book.cover}" width="40" height="50" class="rounded me-2" style="object-fit: cover;">
                                    <div>
                                        <strong>${book.title.substring(0, 40)}${book.title.length > 40 ? '...' : ''}</strong><br>
                                        <small class="text-danger">${book.price.toLocaleString()}đ</small>
                                    </div>
                                </a>
                            `;
                        });
                        suggestDropdown.innerHTML = html;
                        suggestDropdown.style.display = 'block';
                    } else {
                        suggestDropdown.style.display = 'none';
                    }
                });
        }, 300);
    });

    // Ẩn dropdown khi click ra ngoài
    document.addEventListener('click', function(e) {
        if (!searchInput.contains(e.target) && !suggestDropdown.contains(e.target)) {
            suggestDropdown.style.display = 'none';
        }
    });
}