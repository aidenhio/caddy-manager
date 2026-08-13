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