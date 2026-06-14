import React, { useEffect, useState } from "react";
import {
  View,
  Image,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  Alert,
  ActivityIndicator,
  useWindowDimensions,
} from "react-native";

import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import { useRouter, useLocalSearchParams } from "expo-router";

import { api, formatApiError } from "../../src/api";
import { theme, formatCurrency } from "../../src/theme";
import {
  maskDocument,
  maskPhoneBR,
  maskCurrency,
  formatCurrencyFromBackend,
  parseCurrency,
  parseNumber,
} from "../../src/masks";

import UpgradeModal from "../../src/UpgradeModal";

type Product = {
  id: string;
  product_id?: string;
  code?: string;
  name: string;
  description?: string;
  quantity: string;
  price: string;
};

type CatalogProduct = {
  id: string;
  code: string;
  name: string;
  description: string;
  price: number;
  unit: string;
};

type ProductItemProps = {
  p: Product;
  i: number;
  productsLength: number;
  focusedIndex: number | null;
  catalogProducts: CatalogProduct[];
  setFocusedIndex: React.Dispatch<React.SetStateAction<number | null>>;
  removeProduct: (i: number) => void;
  updateProduct: (i: number, key: keyof Product, value: string) => void;
  selectCatalogProduct: (itemIndex: number, product: CatalogProduct) => void;
};

export default function NewProposal() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;

  const params = useLocalSearchParams();
  const editId = typeof params.editId === "string" ? params.editId : null;
  const isEditing = !!editId;

  const [clientName, setClientName] = useState("");
  const [doc, setDoc] = useState("");
  const [phone, setPhone] = useState("");
  const [deadline, setDeadline] = useState("");
  const [notes, setNotes] = useState("");
  const [discount, setDiscount] = useState("");
  const [paymentTerms, setPaymentTerms] = useState("");
  const [validity, setValidity] = useState("15");
  const [images, setImages] = useState<string[]>([]);
  
  const [products, setProducts] = useState<Product[]>([
  {
    id: crypto.randomUUID(),
    name: "",
    quantity: "",
    price: "",
    description: "",
  },
]);

  const [catalogProducts, setCatalogProducts] = useState<CatalogProduct[]>([]);
  const [loadingCatalog, setLoadingCatalog] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingProposal, setLoadingProposal] = useState(false);
  const [upgradeOpen, setUpgradeOpen] = useState(false);
  const [upgradeMsg, setUpgradeMsg] = useState<string | undefined>();
  
  // Controla qual item está com o dropdown ativo focado para evitar sobreposição visual
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);

  const reset = () => {
    setClientName("");
    setDoc("");
    setPhone("");
    setDeadline("");
    setNotes("");
    setDiscount("");
    setPaymentTerms("");
    setValidity("15");
    setImages([]);
    setProducts([
	  {
		id: crypto.randomUUID(),
		name: "",
		quantity: "",
		price: "",
		description: "",
	  },
	]);
};
  useEffect(() => {
    if (!editId) {
      reset();
      return;
    }

    const loadProposal = async () => {
      try {
        setLoadingProposal(true);
        const { data } = await api.get(`/proposals/${editId}`);

        setClientName(data.client_name || "");
        setDoc(data.client_document || "");
        setPhone(data.client_phone || "");
        setDeadline(data.shipping_deadline || "");
        setNotes(data.notes || "");
        setDiscount(formatCurrencyFromBackend(data.discount || ""));
        setPaymentTerms(data.payment_terms || "");
        setValidity(String(data.validity_days || 15));
        setImages(Array.isArray(data.images) ? data.images : []);

        if (data.products && data.products.length) {
          setProducts(
			data.products.map((p: any) => ({
			  id: crypto.randomUUID(),
			  product_id: p.product_id || undefined,
			  code: p.code || undefined,
			  name: p.name || "",
			  description: p.description || "",
			  quantity: String(p.quantity || ""),
			  price: formatCurrencyFromBackend(p.price || ""),
			}))
		  );
        }
      } catch (e) {
        Alert.alert("Erro", "Não foi possí­vel carregar proposta");
      } finally {
        setLoadingProposal(false);
      }
    };

    loadProposal();
  }, [editId]);

  useEffect(() => {
    const loadCatalog = async () => {
      try {
        setLoadingCatalog(true);
        const { data } = await api.get("/products");
        setCatalogProducts(Array.isArray(data) ? data : []); 	
      } catch (e) {
        console.log("Erro carregando catálogo", e);
      } finally {
        setLoadingCatalog(false);
      }
    };

    loadCatalog();
  }, []);

	const addProduct = () => {
  setProducts((prev) => [
    ...prev,
    {
      id: crypto.randomUUID(),
      name: "",
      quantity: "",
      price: "",
      description: "",
    },
  ]);
};

  const removeProduct = (i: number) => {
    if (products.length === 1) return;
    setProducts((prev) => prev.filter((_, idx) => idx !== i));
    if (focusedIndex === i) setFocusedIndex(null);
  };

  const updateProduct = (i: number, key: keyof Product, value: string) => {
  console.log("UPDATE", i, key, value);

  setProducts((prev) =>
    prev.map((p, idx) =>
      idx === i
        ? { ...p, [key]: value }
        : p
    )
  );
};

  const selectCatalogProduct = (itemIndex: number, product: CatalogProduct) => {
    setProducts((prev) =>
      prev.map((p, idx) =>
        idx === itemIndex
          ? {
              ...p,
              product_id: product.id,
              code: product.code,
              name: product.name,
              description: product.description,
              price: formatCurrencyFromBackend(product.price),
            }
          : p
      )
    );
    setFocusedIndex(null); // Fecha o dropdown imediatamente após a seleção
  };

  const buildUploadForm = async (asset: any) => {
    const form = new FormData();
    if (Platform.OS === "web") {
      const response = await fetch(asset.uri);
      const blob = await response.blob();
      const name = asset.fileName || asset.uri?.split("/").pop() || "image.jpg";
      form.append("file", blob, name);
    } else {
      form.append("file", {
        uri: asset.uri,
        type: asset.type || "image/jpeg",
        name: asset.fileName || "image.jpg",
      } as any);
    }
    return form;
  };

  const pickImages = async () => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.7,
        allowsMultipleSelection: true,
      });

      if (result.canceled) return;

      setSaving(true);
      const uploaded: string[] = [];

      for (const asset of result.assets) {
        const form = await buildUploadForm(asset);
        const res = await api.post("/upload/image", form);
        uploaded.push(res.data.url);
      }

      setImages((prev) => [...prev, ...uploaded]);
    } catch (e) {
      Alert.alert("Erro", "Falha ao enviar imagens");
    } finally {
      setSaving(false);
    }
  };

  const removeImage = (url: string) => {
    setImages((prev) => prev.filter((i) => i !== url));
  };

  const subtotal = products.reduce(
    (acc, p) => acc + (parseNumber(p.quantity) || 0) * (parseCurrency(p.price) || 0),
    0
  );
  const discountNum = parseCurrency(discount);
  const total = Math.max(subtotal - discountNum, 0);

  const submit = async () => {
	  console.log("SUBMIT EXECUTOU");
    if (!clientName || !doc || !phone || !deadline) {
      Alert.alert("Atenção", "Preencha cliente, CNPJ/CPF, telefone e prazo.");
      return;
    }

    const cleanProducts = products
  .filter((p) =>
    p.name?.trim() ||
    p.description?.trim()
  )
  .map((p) => ({
        product_id: p.product_id || undefined,
        code: p.code || undefined,
        name: p.name.trim(),
        description: p.description?.trim() || undefined,
        quantity: parseNumber(p.quantity),
        price: parseCurrency(p.price),
      }));
	  console.log("STATE PRODUCTS", products);
	  console.log("PRODUTOS", cleanProducts);
    if (!cleanProducts.length) {
      Alert.alert("Atenção", "Adicione pelo menos 1 produto.");
      return;
    }

    try {
      setSaving(true);
	  console.log("PRODUTOS", cleanProducts);
      const payload = {
        client_name: clientName.trim(),
        client_document: doc.trim(),
        client_phone: phone.trim(),
        products: cleanProducts,
        shipping_deadline: deadline.trim(),
        notes: notes.trim(),
        discount: discountNum,
        payment_terms: paymentTerms.trim(),
        images,
        validity_days: parseInt(validity || "15", 10) || 15,
      };
	  console.log("PAYLOAD", payload);
      let response;
      if (isEditing && editId) {
        response = await api.put(`/proposals/${editId}`, payload);
      } else {
	  console.log("ENVIANDO PARA API");
        response = await api.post("/proposals", payload);
	 response = await api.post("/proposals", payload);
      console.log("RESPOSTA API", response.data); 
      }

      reset();
      router.replace(`/proposal/${response.data.id}`);
    } catch (e: any) {
      if (e?.response?.status === 402) {
        setUpgradeMsg(e.response.data?.detail);
        setUpgradeOpen(true);
      } else {
        Alert.alert("Erro", formatApiError(e));
      }
    } finally {
      setSaving(false);
    }
  };

  if (loadingProposal) {
    return (
      <SafeAreaView style={s.root}>
        <ActivityIndicator style={{ marginTop: 80 }} color={theme.colors.primary} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.root} edges={["top"]} testID="new-proposal-screen">
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={{ flex: 1 }}
      >
        <View style={s.header}>
          <Text style={s.title}>{isEditing ? "Editar proposta" : "Nova proposta"}</Text>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 4 }}>
            <Text style={s.subtitle}>Preencha rápido e envie no WhatsApp</Text>
            {loadingCatalog && <ActivityIndicator size="small" color={theme.colors.primary} />}
          </View>
        </View>

        <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
          {isDesktop ? (
            <View style={s.desktopColumns}>
              <View style={s.desktopColumn}>
                <View style={s.panelCard}>
                  <Section title="Cliente">
                    <Input
                      label="Nome *"
                      value={clientName}
                      onChangeText={setClientName}
                      placeholder="Nome do cliente"
                    />

                    <Input
                      label="CNPJ / CPF *"
                      value={doc}
                      onChangeText={(v: string) => setDoc(maskDocument(v))}
                      keyboardType="number-pad"
                      placeholder="000.000.000-00"
                    />

                    <Input
                      label="Telefone *"
                      value={phone}
                      onChangeText={(v: string) => setPhone(maskPhoneBR(v))}
                      keyboardType="phone-pad"
                      placeholder="(11) 99999-9999"
                    />
                  </Section>
                </View>

                <View style={s.panelCard}>
                  <Section
                    title="Itens"
                    right={
                      <TouchableOpacity onPress={addProduct}>
                        <Text style={s.link}>+ Adicionar</Text>
                      </TouchableOpacity>
                    }
                  >
                    {products.map((p, i) => (
                      <ProductItem
                        key={p.id}
                        p={p}
                        i={i}
                        productsLength={products.length}
                        focusedIndex={focusedIndex}
                        catalogProducts={catalogProducts}
                        setFocusedIndex={setFocusedIndex}
                        removeProduct={removeProduct}
                        updateProduct={updateProduct}
                        selectCatalogProduct={selectCatalogProduct}
                      />
                    ))}
                  </Section>
                </View>
              </View>

              <View style={s.desktopColumn}>
                <View style={s.panelCard}>
                  <Text style={s.sectionTitle}>Resumo financeiro</Text>
                  <View style={s.summaryItem}>
                    <Text style={s.summaryLabel}>Subtotal</Text>
                    <Text style={s.summaryValue}>{formatCurrency(subtotal)}</Text>
                  </View>
                  <View style={s.summaryItem}>
                    <Text style={s.summaryLabel}>Desconto</Text>
                    <Text style={s.summaryValue}>{formatCurrency(discountNum)}</Text>
                  </View>
                  <View style={s.summaryItem}>
                    <Text style={s.summaryLabel}>Total</Text>
                    <Text style={s.summaryValue}>{formatCurrency(total)}</Text>
                  </View>
                </View>

                <View style={s.panelCard}>
                  <Section title="Imagens">
                    <TouchableOpacity style={s.imageButton} onPress={pickImages}>
                      <Ionicons name="image-outline" size={22} color="#fff" />
                      <Text style={s.imageButtonText}>Adicionar imagens</Text>
                    </TouchableOpacity>

                    {!!images.length && (
                      <ScrollView
                        horizontal
                        showsHorizontalScrollIndicator={false}
                        contentContainerStyle={{ gap: 10, marginTop: 10 }}
                      >
                        {images.map((img) => (
                          <View key={img} style={s.imageWrap}>
                            <Image source={{ uri: img }} style={s.image} />
                            <TouchableOpacity style={s.removeImage} onPress={() => removeImage(img)}>
                              <Ionicons name="close" size={16} color="#fff" />
                            </TouchableOpacity>
                          </View>
                        ))}
                      </ScrollView>
                    )}
                  </Section>
                </View>

                <View style={s.panelCard}>
                  <Section title="Condições">
                    <Input
                      label="Prazo de embarque *"
                      value={deadline}
                      onChangeText={setDeadline}
                      placeholder="Ex: 15 dias Úteis"
                    />

                    <Input
                      label="Condições de pagamento"
                      value={paymentTerms}
                      onChangeText={setPaymentTerms}
                      placeholder="Ex: 30/60/90 dias"
                    />

                    <View style={{ flexDirection: "row", gap: 8 }}>
                      <View style={{ flex: 1 }}>
                        <Input
                          label="Desconto (R$)"
                          value={discount}
                          onChangeText={(v: string) => setDiscount(maskCurrency(v))}
                          keyboardType="numeric"
                          placeholder="0,00"
                        />
                      </View>

                      <View style={{ flex: 1 }}>
                        <Input
                          label="Validade (dias)"
                          value={validity}
                          onChangeText={(v: string) =>
                            setValidity(v.replace(/\D/g, "").slice(0, 3))
                          }
                          keyboardType="number-pad"
                          placeholder="15"
                        />
                      </View>
                    </View>

                    <Input
                      label="Observações"
                      value={notes}
                      onChangeText={setNotes}
                      placeholder="Opcional"
                      multiline
                    />
                  </Section>
                </View>

                <TouchableOpacity
                  style={[s.cta, saving && { opacity: 0.7 }]}
                  onPress={submit}
                  disabled={saving}
                >
                  {saving ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <>
                      <Ionicons name="checkmark-circle" size={22} color="#fff" />
                      <Text style={s.ctaText}>
                        {isEditing ? "Salvar alterações" : "Criar proposta"}
                      </Text>
                    </>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          ) : (
            <>
              <Section title="Cliente">
                <Input
                  label="Nome *"
                  value={clientName}
                  onChangeText={setClientName}
                  placeholder="Nome do cliente"
                />

                <Input
                  label="CNPJ / CPF *"
                  value={doc}
                  onChangeText={(v: string) => setDoc(maskDocument(v))}
                  keyboardType="number-pad"
                  placeholder="000.000.000-00"
                />

                <Input
                  label="Telefone *"
                  value={phone}
                  onChangeText={(v: string) => setPhone(maskPhoneBR(v))}
                  keyboardType="phone-pad"
                  placeholder="(11) 99999-9999"
                />
              </Section>

              <Section
                title="Itens"
                right={
                  <TouchableOpacity onPress={addProduct}>
                    <Text style={s.link}>+ Adicionar</Text>
                  </TouchableOpacity>
                }
              >
                {products.map((p, i) => (
                  <ProductItem
                    key={p.id}
                    p={p}
                    i={i}
                    productsLength={products.length}
                    focusedIndex={focusedIndex}
                    catalogProducts={catalogProducts}
                    setFocusedIndex={setFocusedIndex}
                    removeProduct={removeProduct}
                    updateProduct={updateProduct}
                    selectCatalogProduct={selectCatalogProduct}
                  />
                ))}
              </Section>

              <Section title="Imagens">
                <TouchableOpacity style={s.imageButton} onPress={pickImages}>
                  <Ionicons name="image-outline" size={22} color="#fff" />
                  <Text style={s.imageButtonText}>Adicionar imagens</Text>
                </TouchableOpacity>

                {!!images.length && (
                  <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={{ gap: 10, marginTop: 10 }}
                  >
                    {images.map((img) => (
                      <View key={img} style={s.imageWrap}>
                        <Image source={{ uri: img }} style={s.image} />
                        <TouchableOpacity style={s.removeImage} onPress={() => removeImage(img)}>
                          <Ionicons name="close" size={16} color="#fff" />
                        </TouchableOpacity>
                      </View>
                    ))}
                  </ScrollView>
                )}
              </Section>

              <Section title="Condições">
                <Input
                  label="Prazo de embarque *"
                  value={deadline}
                  onChangeText={setDeadline}
                  placeholder="Ex: 15 dias úteis"
                />

                <Input
                  label="Condições de pagamento"
                  value={paymentTerms}
                  onChangeText={setPaymentTerms}
                  placeholder="Ex: 30/60/90 dias"
                />

                <View style={{ flexDirection: "row", gap: 8 }}>
                  <View style={{ flex: 1 }}>
                    <Input
                      label="Desconto (R$)"
                      value={discount}
                      onChangeText={(v: string) => setDiscount(maskCurrency(v))}
                      keyboardType="numeric"
                      placeholder="0,00"
                    />
                  </View>

                  <View style={{ flex: 1 }}>
                    <Input
                      label="Validade (dias)"
                      value={validity}
                      onChangeText={(v: string) =>
                        setValidity(v.replace(/\D/g, "").slice(0, 3))
                      }
                      keyboardType="number-pad"
                      placeholder="15"
                    />
                  </View>
                </View>

                <Input
                  label="Observações"
                  value={notes}
                  onChangeText={setNotes}
                  placeholder="Opcional"
                  multiline
                />
              </Section>

              <View style={s.totalBox}>
                <View style={{ flex: 1 }}>
                  <Text style={s.totalLabel}>Subtotal</Text>
                  <Text style={s.subValue}>{formatCurrency(subtotal)}</Text>
                  {discountNum > 0 && (
                    <Text style={s.subValue}>- {formatCurrency(discountNum)} desconto</Text>
                  )}
                </View>

                <View style={{ alignItems: "flex-end" }}>
                  <Text style={s.totalLabel}>Total</Text>
                  <Text style={s.totalValue}>{formatCurrency(total)}</Text>
                </View>
              </View>
            </>
          )}
        </ScrollView>

        {!isDesktop && (
          <View style={s.bottom}>
            <TouchableOpacity
              style={[s.cta, saving && { opacity: 0.7 }]}
              onPress={submit}
              disabled={saving}
            >
              {saving ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <>
                  <Ionicons name="checkmark-circle" size={22} color="#fff" />
                  <Text style={s.ctaText}>
                    {isEditing ? "Salvar alterações" : "Criar proposta"}
                  </Text>
                </>
              )}
            </TouchableOpacity>
          </View>
        )}
      </KeyboardAvoidingView>

      <UpgradeModal
        visible={upgradeOpen}
        message={upgradeMsg}
        onClose={() => setUpgradeOpen(false)}
      />
    </SafeAreaView>
  );
}

const ProductItem = React.memo(function ProductItem({
  p,
  i,
  productsLength,
  focusedIndex,
  catalogProducts,
  setFocusedIndex,
  removeProduct,
  updateProduct,
  selectCatalogProduct,
}: ProductItemProps) {
  console.log("RENDER PRODUCT ITEM", p.id);
  const showDropdown = focusedIndex === i && catalogProducts.length > 0;

  // Filtro aprimorado: busca por codigo ou nome.
  const search = p.name.toLowerCase().trim();

  const filteredCatalog = !search
    ? catalogProducts
    : catalogProducts.filter((cp) => {
        const cpCode = cp.code.toLowerCase();
        const cpName = cp.name.toLowerCase();

        return cpCode.includes(search) || cpName.includes(search);
      });

  return (
    <View style={s.product}>
      <View style={s.productHeader}>
        <Text style={s.productHeaderText}>Item {i + 1}</Text>
        {productsLength > 1 && (
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
});

function Section({ title, right, children }: any) {
  return (
    <View style={s.section}>
      <View style={s.sectionHead}>
        <Text style={s.sectionTitle}>{title}</Text>
        {right}
      </View>
      <View style={{ gap: 10 }}>{children}</View>
    </View>
  );
}

function Input({ label, customHeight, ...props }: any) {
  console.log("RENDER INPUT", label);
  return (
    <View style={{ gap: 6, width: "100%" }}>
      <Text style={s.label}>{label}</Text>

      <TextInput
  value={props.value}
  onChangeText={props.onChangeText}
  onFocus={(event) => {
    console.log("FOCUS", label);
    props.onFocus?.(event);
  }}
  onBlur={(event) => {
    console.log("BLUR", label);
    props.onBlur?.(event);
  }}
  placeholder={props.placeholder}
  keyboardType={props.keyboardType}
  multiline={props.multiline}
  placeholderTextColor={theme.colors.textMuted}
  style={[
    s.input,
    props.multiline && {
      height: customHeight || 80,
      paddingTop: 12,
      textAlignVertical: "top",
    },
  ]}
/>
    </View>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: theme.colors.bg,
  },
  header: {
    paddingHorizontal: 24,
    paddingTop: 12,
  },
  title: {
    fontSize: 28,
    fontWeight: "800",
    color: theme.colors.text,
  },
  subtitle: {
    fontSize: 13,
    color: theme.colors.textSec,
  },
  scroll: {
    padding: 24,
    paddingBottom: 140,
    gap: 16,
  },
  desktopColumns: {
    flexDirection: "row",
    gap: 20,
    alignItems: "flex-start",
  },
  desktopColumn: {
    flex: 1,
    gap: 20,
    minWidth: 420,
  },
  panelCard: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 20,
    padding: 20,
    gap: 16,
  },
  summaryItem: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 12,
  },
  summaryLabel: {
    color: theme.colors.textSec,
    fontSize: 13,
  },
  summaryValue: {
    color: theme.colors.text,
    fontSize: 16,
    fontWeight: "700",
  },
  section: {
    gap: 10,
  },
  sectionHead: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.textMuted,
    letterSpacing: 1.5,
    textTransform: "uppercase",
  },
  link: {
    color: theme.colors.text,
    fontWeight: "700",
    fontSize: 14,
  },
  label: {
    fontSize: 11,
    color: theme.colors.textMuted,
    fontWeight: "700",
    letterSpacing: 0.5,
    textTransform: "uppercase",
  },
  input: {
    height: 52,
    borderRadius: 12,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    paddingHorizontal: 14,
    fontSize: 16,
    color: theme.colors.text,
  },
  product: {
    padding: 14,
    backgroundColor: "#F1F5F9",
    borderRadius: 14,
    gap: 10,
    marginBottom: 10,
  },
  productHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  productHeaderText: {
    fontWeight: "700",
    color: theme.colors.text,
  },
  totalBox: {
    marginTop: 8,
    padding: 20,
    backgroundColor: theme.colors.primary,
    borderRadius: 16,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  totalLabel: {
    color: "#94A3B8",
    fontSize: 11,
    letterSpacing: 1.5,
    textTransform: "uppercase",
    fontWeight: "700",
  },
  totalValue: {
    color: "#fff",
    fontSize: 26,
    fontWeight: "800",
    marginTop: 4,
  },
  subValue: {
    color: "rgba(255,255,255,0.7)",
    fontSize: 14,
    marginTop: 4,
  },
  imageButton: {
    height: 52,
    borderRadius: 12,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 8,
  },
  imageButtonText: {
    color: "#fff",
    fontWeight: "700",
    fontSize: 15,
  },
  imageWrap: {
    position: "relative",
  },
  image: {
    width: 120,
    height: 120,
    borderRadius: 14,
  },
  removeImage: {
    position: "absolute",
    top: 6,
    right: 6,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: "rgba(0,0,0,0.7)",
    alignItems: "center",
    justifyContent: "center",
  },
  bottom: {
    position: "absolute",
    left: 16,
    right: 16,
    bottom: 16,
  },
  cta: {
    height: 56,
    borderRadius: 12,
    backgroundColor: theme.colors.primary,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  ctaText: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "700",
  },
  catalogList: {
    marginTop: 4,
    backgroundColor: "#fff",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: theme.colors.border,
    maxHeight: 200,
    overflow: "hidden",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  catalogItem: {
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#F1F5F9",
  },
  catalogItemText: {
    color: theme.colors.text,
    fontSize: 14,
  },
});

