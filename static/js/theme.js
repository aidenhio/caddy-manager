const themeConfig = {
	"theme": "light",
}

const params = new Proxy(new URLSearchParams(window.location.search), {
	get: (searchParams, prop) => searchParams.get(prop),
})

for (const key in themeConfig) {
	const param = params[key]
	let selectedValue

	if (!!param) {
		localStorage.setItem(key, param)
		selectedValue = param
	} else {
		const storedTheme = localStorage.getItem(key)
		selectedValue = storedTheme ? storedTheme : themeConfig[key]
	}

	if (selectedValue !== themeConfig[key]) {
		document.documentElement.setAttribute('data-bs-' + key, selectedValue)
	} else {
		document.documentElement.removeAttribute('data-bs-' + key)
	}
}

// Theme links (?theme=dark|light) switch in place instead of reloading; the href still works without JS.
document.addEventListener('click', (event) => {
	const link = event.target.closest('[data-theme-value]')
	if (!link) return
	event.preventDefault()
	const theme = link.dataset.themeValue
	localStorage.setItem('theme', theme)
	if (theme === themeConfig.theme) {
		document.documentElement.removeAttribute('data-bs-theme')
	} else {
		document.documentElement.setAttribute('data-bs-theme', theme)
	}
})