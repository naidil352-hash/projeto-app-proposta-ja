 // Subcomponente dinâmico compartilhado para renderizar os itens (Desktop e Mobile)
	const ProductItem = React.memo(function ProductItem({ p, i }: { p: Product; i: number }) {
	useEffect(() => {
  console.log("MOUNT PRODUCT ITEM");

  return () => {
    console.log("UNMOUNT PRODUCT ITEM");
  };
}, []);
	console.log("RENDER PRODUCT ITEM", p.id);
    const showDropdown =
	  focusedIndex === i &&
	  catalogProducts.length > 0;

    // Filtro aprimorado: Busca por código exato primeiro, depois por aproximação de string
	const search =
	  p.name.toLowerCase().trim();

	const filteredCatalog =
	  !search
      ? catalogProducts
      : catalogProducts.filter((cp) => {
        const cpCode =
          cp.code.toLowerCase();

        const cpName =
          cp.name.toLowerCase();

        return (
          cpCode.includes(search) ||
          cpName.includes(search)
        );
      });

    return (
      <View style={s.product}>
        <View style={s.productHeader}>
          <Text style={s.productHeaderText}>Item {i + 1}</Text>
          {products.length > 1 && (
            <TouchableOpacity onPress={() => removeProduct(i)}>
              <Ionicons name="trash-outline" size={18} color={theme.colors.danger} />
            </TouchableOpacity>
          )}
        </View>

        <View style={{ zIndex: 100 - i }}>
          <Input
            label="Produto"
            value={p.name}
            onFocus={() => setFocusedIndex(i)}
            onChangeText={(v: string) => updateProduct(i, "name", v)}
            placeholder="Nome ou código do produto"
          />

          {showDropdown && filteredCatalog.length > 0 && (
            <View style={s.catalogList}>
              {filteredCatalog.slice(0, 10).map((cp) => (
                <TouchableOpacity
                  key={cp.id}
                  style={s.catalogItem}
                  onPress={() => selectCatalogProduct(i, cp)}
                >
                  <Text style={s.catalogItemText}>
                    <Text style={{ fontWeight: "bold" }}>{cp.code}</Text> - {cp.name}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          )}
        </View>

        <Input
          label="Descrição"
          value={p.description || ""}
          onChangeText={(v: string) => updateProduct(i, "description", v)}
          placeholder="Descrição técnica (opcional)"
          multiline
          customHeight={60}
        />

        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}>
            <Input
              label="Qtd"
              value={p.quantity}
              onChangeText={(v: string) =>
                updateProduct(i, "quantity", v.replace(/[^0-9,.]/g, ""))
              }
              keyboardType="numeric"
              placeholder="0"
            />
          </View>

          <View style={{ flex: 1.4 }}>
            <Input
              label="Preço un."
              value={p.price}
              onChangeText={(v: string) => updateProduct(i, "price", maskCurrency(v))}
              keyboardType="numeric"
              placeholder="0,00"
            />
          </View>
        </View>
      </View>
    );
  }
);