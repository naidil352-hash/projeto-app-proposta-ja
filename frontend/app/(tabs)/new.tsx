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
import { useAuth } from "../../src/auth";
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
  unit?: string;
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

export default function NewProposal() {
  const router = useRouter();
  const { user } = useAuth();
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
  
  const [clientEmail, setClientEmail] = useState("");
  const [clientCompany, setClientCompany] = useState("");
  const [clientCity, setClientCity] = useState("");
  const [clientState, setClientState] = useState("");
  const [clientAddress, setClientAddress] = useState("");
  const [clientId, setClientId] = useState("");

  // New Commercial Conditions State Variables
  const [shippingType, setShippingType] = useState("");
  const [shippingResponsible, setShippingResponsible] = useState("");
  const [shippingCompany, setShippingCompany] = useState("");
  const [manufacturingDays, setManufacturingDays] = useState("");
  const [deliveryDays, setDeliveryDays] = useState("");
  const [warranty, setWarranty] = useState("");
  const [deliveryPlace, setDeliveryPlace] = useState("");
  const [incoterm, setIncoterm] = useState("");
  const [currency, setCurrency] = useState("BRL");
  const [commercialConditions, setCommercialConditions] = useState("");
  const [internalNotes, setInternalNotes] = useState("");

  const [templates, setTemplates] = useState<any[]>([]);

  const applyTemplate = (tpl: any) => {
    if (!tpl) return;
    setPaymentTerms(tpl.payment_terms || "");
    setShippingType(tpl.shipping_type || "");
    setShippingResponsible(tpl.shipping_responsible || "");
    setShippingCompany(tpl.shipping_company || "");
    setManufacturingDays(tpl.manufacturing_days || "");
    setDeliveryDays(tpl.delivery_days || "");
    setWarranty(tpl.warranty || "");
    setValidity(String(tpl.validity_days || 15));
    setIncoterm(tpl.incoterm || "");
    setCurrency(tpl.currency || "BRL");
    setCommercialConditions(tpl.commercial_conditions || "");
    setInternalNotes(tpl.internal_notes || "");
  };

  const loadTemplatesAndDefaults = async () => {
    try {
      const { data } = await api.get("/commercial-templates");
      setTemplates(data || []);
      
      // If we are in creation mode, find the default template and pre-fill fields
      if (!editId && data && data.length > 0) {
        const defTpl = data.find((t: any) => t.is_default) || data[0];
        applyTemplate(defTpl);
      }
    } catch (e) {
      console.log("Error loading templates:", e);
    }
  };
  
  const [products, setProducts] = useState<Product[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCatalogProduct, setSelectedCatalogProduct] = useState<CatalogProduct | null>(null);
  const [quantityInput, setQuantityInput] = useState("1");
  const [showDropdown, setShowDropdown] = useState(false);

  const [itemType, setItemType] = useState<"catalog" | "manual">("catalog");
  const [manualName, setManualName] = useState("");
  const [manualDesc, setManualDesc] = useState("");
  const [manualUnit, setManualUnit] = useState("UN");
  const [manualPrice, setManualPrice] = useState("");
  const [manualQty, setManualQty] = useState("1");

  const [catalogProducts, setCatalogProducts] = useState<CatalogProduct[]>([]);
  const [loadingCatalog, setLoadingCatalog] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingProposal, setLoadingProposal] = useState(false);
  const [upgradeOpen, setUpgradeOpen] = useState(false);
  const [upgradeMsg, setUpgradeMsg] = useState<string | undefined>();
  const [editingItemIndex, setEditingItemIndex] = useState<number | null>(null);
  const [editingItem, setEditingItem] = useState<Product | null>(null);
  
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
    setProducts([]);
    setSearchQuery("");
    setSelectedCatalogProduct(null);
    setQuantityInput("1");
    setShowDropdown(false);
    setItemType("catalog");
    setManualName("");
    setManualDesc("");
    setManualUnit("UN");
    setManualPrice("");
    setManualQty("1");
    setShippingType("");
    setShippingResponsible("");
    setShippingCompany("");
    setManufacturingDays("");
    setDeliveryDays("");
    setWarranty("");
    setDeliveryPlace("");
    setIncoterm("");
    setCurrency("BRL");
    setCommercialConditions("");
    setInternalNotes("");
    setClientEmail("");
    setClientCompany("");
    setClientCity("");
    setClientState("");
    setClientAddress("");
    setClientId("");
    setEditingItemIndex(null);
    setEditingItem(null);
  };
  useEffect(() => {
    if (!editId) {
      reset();
      loadTemplatesAndDefaults();

      if (params.clientName) setClientName(decodeURIComponent(String(params.clientName)));
      if (params.clientPhone) setPhone(decodeURIComponent(String(params.clientPhone)));
      if (params.clientDocument) setDoc(decodeURIComponent(String(params.clientDocument)));
      if (params.clientEmail) setClientEmail(decodeURIComponent(String(params.clientEmail)));
      if (params.clientCompany) setClientCompany(decodeURIComponent(String(params.clientCompany)));
      if (params.clientCity) setClientCity(decodeURIComponent(String(params.clientCity)));
      if (params.clientState) setClientState(decodeURIComponent(String(params.clientState)));
      if (params.clientAddress) setClientAddress(decodeURIComponent(String(params.clientAddress)));
      if (params.clientId) setClientId(decodeURIComponent(String(params.clientId)));
      return;
    }

    const loadProposal = async () => {
      try {
        setLoadingProposal(true);
        const { data } = await api.get(`/proposals/${editId}`);

        if (data.acceptance_status === "accepted") {
          Alert.alert("Atenção", "Esta proposta já foi aceita e não pode ser editada.");
          router.replace(`/proposal/${editId}`);
          return;
        }

        setClientName(data.client_name || "");
        setDoc(data.client_document || "");
        setPhone(data.client_phone || "");
        setClientEmail(data.client_email || "");
        setClientCompany(data.client_company || "");
        setClientCity(data.client_city || "");
        setClientState(data.client_state || "");
        setClientAddress(data.client_address || "");
        setClientId(data.client_id || "");
        setDeadline(data.shipping_deadline || "");
        setNotes(data.notes || "");
        setDiscount(formatCurrencyFromBackend(data.discount || ""));
        setPaymentTerms(data.payment_terms || "");
        setValidity(String(data.validity_days || 15));
        setImages(Array.isArray(data.images) ? data.images : []);
        
        setShippingType(data.shipping_type || "");
        setShippingResponsible(data.shipping_responsible || "");
        setShippingCompany(data.shipping_company || "");
        setManufacturingDays(data.manufacturing_days || "");
        setDeliveryDays(data.delivery_days || "");
        setWarranty(data.warranty || "");
        setDeliveryPlace(data.delivery_place || "");
        setIncoterm(data.incoterm || "");
        setCurrency(data.currency || "BRL");
        setCommercialConditions(data.commercial_conditions || "");
        setInternalNotes(data.internal_notes || "");

        if (data.products && data.products.length) {
          setProducts(
            data.products.map((p: any) => ({
              id: crypto.randomUUID(),
              product_id: p.product_id || undefined,
              code: p.code || undefined,
              name: p.name || "",
              description: p.description || "",
              unit: p.unit || "UN",
              quantity: String(p.quantity || ""),
              price: formatCurrencyFromBackend(p.unit_price || p.price || 0),
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

	  const removeProduct = (i: number) => {
    setProducts((prev) => prev.filter((_, idx) => idx !== i));
    if (editingItemIndex === i) {
      setEditingItemIndex(null);
      setEditingItem(null);
    }
  };

  const startEditingItem = (item: Product, index: number) => {
    setEditingItemIndex(index);
    setEditingItem({ ...item });
  };

  const cancelEditingItem = () => {
    setEditingItemIndex(null);
    setEditingItem(null);
  };

  const saveEditingItem = () => {
    if (editingItemIndex === null || !editingItem) return;

    const quantity = parseNumber(editingItem.quantity);
    const unitPrice = parseCurrency(editingItem.price);
    if (!editingItem.name.trim()) {
      Alert.alert("Erro", "O nome do item é obrigatório.");
      return;
    }
    if (quantity <= 0) {
      Alert.alert("Erro", "A quantidade deve ser maior que zero.");
      return;
    }
    if (unitPrice < 0) {
      Alert.alert("Erro", "O preço unitário deve ser maior ou igual a zero.");
      return;
    }

    const updatedItem = {
      ...editingItem,
      name: editingItem.name.trim(),
      description: editingItem.description?.trim() || "",
      unit: editingItem.unit?.trim() || "UN",
      quantity: String(quantity),
      price: formatCurrencyFromBackend(unitPrice),
    };
    setProducts((prev) => prev.map((item, index) => index === editingItemIndex ? updatedItem : item));
    cancelEditingItem();
  };

  const handleAddItem = () => {
    if (itemType === "catalog") {
      if (!selectedCatalogProduct) {
        Alert.alert("Erro", "Selecione um produto do catálogo primeiro.");
        return;
      }
      const qty = parseNumber(quantityInput);
      if (qty <= 0) {
        Alert.alert("Erro", "A quantidade deve ser maior que zero.");
        return;
      }

      setProducts((prev) => {
        const existingIdx = prev.findIndex((p) => p.product_id === selectedCatalogProduct.id);
        if (existingIdx >= 0) {
          return prev.map((p, idx) =>
            idx === existingIdx
              ? {
                  ...p,
                  quantity: String(parseNumber(p.quantity) + qty),
                }
              : p
          );
        }
        return [
          ...prev,
          {
            id: crypto.randomUUID(),
            product_id: selectedCatalogProduct.id,
            code: selectedCatalogProduct.code,
            name: selectedCatalogProduct.name,
            description: selectedCatalogProduct.description,
            unit: selectedCatalogProduct.unit || "UN",
            quantity: String(qty),
            price: formatCurrencyFromBackend(selectedCatalogProduct.price),
          },
        ];
      });

      setSelectedCatalogProduct(null);
      setSearchQuery("");
      setQuantityInput("1");
    } else {
      if (!manualName.trim()) {
        Alert.alert("Erro", "O nome do item é obrigatório.");
        return;
      }
      const qty = parseNumber(manualQty);
      if (qty <= 0) {
        Alert.alert("Erro", "A quantidade deve ser maior que zero.");
        return;
      }
      const parsedPrice = parseCurrency(manualPrice);
      if (parsedPrice < 0) {
        Alert.alert("Erro", "O preço unitário deve ser maior ou igual a zero.");
        return;
      }

      setProducts((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          name: manualName.trim(),
          description: manualDesc.trim(),
          unit: manualUnit.trim() || "UN",
          quantity: String(qty),
          price: formatCurrencyFromBackend(parsedPrice),
        },
      ]);

      setManualName("");
      setManualDesc("");
      setManualUnit("UN");
      setManualPrice("");
      setManualQty("1");
    }
  };

  const renderItemsSection = () => {
    const search = searchQuery.toLowerCase().trim();
    const filteredCatalog = !search
      ? catalogProducts
      : catalogProducts.filter((cp) => {
          const cpCode = cp.code.toLowerCase();
          const cpName = cp.name.toLowerCase();
          return cpCode.includes(search) || cpName.includes(search);
        });

    return (
      <View style={{ gap: 12 }}>
        {/* Selector Tabs */}
        <View style={{ flexDirection: "row", gap: 8 }}>
          <TouchableOpacity
            style={[
              s.tabButton,
              itemType === "catalog" && s.tabButtonActive
            ]}
            onPress={() => setItemType("catalog")}
          >
            <Text style={[s.tabButtonText, itemType === "catalog" && s.tabButtonTextActive]}>
              + Produto do Catálogo
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[
              s.tabButton,
              itemType === "manual" && s.tabButtonActive
            ]}
            onPress={() => setItemType("manual")}
          >
            <Text style={[s.tabButtonText, itemType === "manual" && s.tabButtonTextActive]}>
              + Item Avulso
            </Text>
          </TouchableOpacity>
        </View>

        <View style={s.selectorBox}>
          {itemType === "catalog" ? (
            <>
              <View style={{ zIndex: 999 }}>
                <Input
                  label="Buscar Produto no Catálogo"
                  value={searchQuery}
                  onChangeText={(v: string) => {
                    setSearchQuery(v);
                    setShowDropdown(true);
                  }}
                  onFocus={() => setShowDropdown(true)}
                  placeholder="Nome ou código do produto..."
                />
                {showDropdown && filteredCatalog.length > 0 && (
                  <View style={s.catalogList}>
                    <ScrollView keyboardShouldPersistTaps="handled" style={{ maxHeight: 200 }}>
                      {filteredCatalog.slice(0, 10).map((cp) => (
                        <TouchableOpacity
                          key={cp.id}
                          style={s.catalogItem}
                          onPress={() => {
                            setSelectedCatalogProduct(cp);
                            setSearchQuery(cp.code + " - " + cp.name);
                            setShowDropdown(false);
                          }}
                        >
                          <Text style={s.catalogItemText}>
                            <Text style={{ fontWeight: "bold" }}>{cp.code}</Text> - {cp.name} ({formatCurrency(cp.price)})
                          </Text>
                        </TouchableOpacity>
                      ))}
                    </ScrollView>
                  </View>
                )}
              </View>

              {selectedCatalogProduct && (
                <View style={s.selectedProductInfo}>
                  <Text style={s.selectedProductText}>
                    Selecionado: {selectedCatalogProduct.code} - {selectedCatalogProduct.name} ({formatCurrency(selectedCatalogProduct.price)})
                  </Text>
                </View>
              )}

              <View style={{ flexDirection: "row", gap: 8, alignItems: "flex-end", marginTop: 4 }}>
                <View style={{ flex: 1 }}>
                  <Input
                    label="Qtd"
                    value={quantityInput}
                    onChangeText={(v: string) => setQuantityInput(v.replace(/[^0-9,.]/g, ""))}
                    keyboardType="numeric"
                    placeholder="1"
                  />
                </View>
                <TouchableOpacity style={s.addButton} onPress={handleAddItem}>
                  <Text style={s.addButtonText}>Adicionar</Text>
                </TouchableOpacity>
              </View>
            </>
          ) : (
            <>
              <Input
                label="Nome *"
                value={manualName}
                onChangeText={setManualName}
                placeholder="Ex: Serpentina FCU 12TR"
              />
              <Input
                label="Descrição"
                value={manualDesc}
                onChangeText={setManualDesc}
                placeholder="Ex: 8 filas tubo 3/8"
              />
              <View style={{ flexDirection: "row", gap: 8 }}>
                <View style={{ flex: 1 }}>
                  <Input
                    label="Unidade"
                    value={manualUnit}
                    onChangeText={setManualUnit}
                    placeholder="UN"
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Input
                    label="Preço Unitário *"
                    value={manualPrice}
                    onChangeText={(v: string) => setManualPrice(maskCurrency(v))}
                    keyboardType="numeric"
                    placeholder="0,00"
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Input
                    label="Qtd *"
                    value={manualQty}
                    onChangeText={(v: string) => setManualQty(v.replace(/[^0-9,.]/g, ""))}
                    keyboardType="numeric"
                    placeholder="1"
                  />
                </View>
              </View>
              <TouchableOpacity style={[s.addButton, { marginTop: 4 }]} onPress={handleAddItem}>
                <Text style={s.addButtonText}>Adicionar Item Avulso</Text>
              </TouchableOpacity>
            </>
          )}
        </View>

        <Text style={s.sectionTitle}>Itens Adicionados</Text>
        {products.length === 0 ? (
          <Text style={{ color: theme.colors.textMuted, fontStyle: "italic", marginVertical: 8 }}>
            Nenhum item adicionado à proposta.
          </Text>
        ) : (
          products.map((p, i) => editingItemIndex === i && editingItem ? (
            <View key={p.id} style={s.itemEditor}>
              {p.product_id ? <Text style={s.catalogLinkNotice}>Vinculado ao catálogo: {p.code || p.product_id}</Text> : null}
              <TextInput style={s.itemEditorInput} value={editingItem.name} onChangeText={(name) => setEditingItem((current) => current ? { ...current, name } : current)} placeholder="Nome" />
              <TextInput style={[s.itemEditorInput, s.itemEditorDescription]} value={editingItem.description || ""} onChangeText={(description) => setEditingItem((current) => current ? { ...current, description } : current)} placeholder="Descrição" multiline />
              <View style={s.itemEditorFields}>
                <TextInput style={[s.itemEditorInput, s.itemEditorField]} value={editingItem.quantity} onChangeText={(quantity) => setEditingItem((current) => current ? { ...current, quantity: quantity.replace(/[^0-9,.]/g, "") } : current)} placeholder="Quantidade" keyboardType="decimal-pad" />
                <TextInput style={[s.itemEditorInput, s.itemEditorField]} value={editingItem.price} onChangeText={(price) => setEditingItem((current) => current ? { ...current, price: maskCurrency(price) } : current)} placeholder="Preço unitário" keyboardType="decimal-pad" />
                <TextInput style={[s.itemEditorInput, s.itemEditorField]} value={editingItem.unit || ""} onChangeText={(unit) => setEditingItem((current) => current ? { ...current, unit } : current)} placeholder="Unidade" autoCapitalize="characters" />
              </View>
              <View style={s.itemEditorActions}>
                <TouchableOpacity style={s.itemEditorCancel} onPress={cancelEditingItem}><Text style={s.itemEditorCancelText}>Cancelar</Text></TouchableOpacity>
                <TouchableOpacity style={s.itemEditorSave} onPress={saveEditingItem}><Text style={s.itemEditorSaveText}>Salvar item</Text></TouchableOpacity>
              </View>
            </View>
          ) : (
            <View key={p.id} style={s.addedProductRow}>
              <View style={{ flex: 1 }}>
                <Text style={s.addedProductTitle}>
                  {p.code ? (
                    <>
                      <Text style={{ fontWeight: "bold" }}>{p.code}</Text> -{" "}
                    </>
                  ) : null}
                  {p.name}
                </Text>
                {p.description ? (
                  <Text style={s.addedProductDesc}>{p.description}</Text>
                ) : null}
                <Text style={s.addedProductSub}>
                  {p.quantity} Qtd × {formatCurrency(parseCurrency(p.price))} {p.unit ? `(${p.unit})` : ""}
                </Text>
              </View>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
                <Text style={s.addedProductTotal}>
                  {formatCurrency((parseNumber(p.quantity) || 0) * (parseCurrency(p.price) || 0))}
                </Text>
                <TouchableOpacity onPress={() => startEditingItem(p, i)} accessibilityLabel={`Editar ${p.name}`}>
                  <Ionicons name="create-outline" size={20} color={theme.colors.primary} />
                </TouchableOpacity>
                <TouchableOpacity onPress={() => removeProduct(i)}>
                  <Ionicons name="trash-outline" size={20} color={theme.colors.danger} />
                </TouchableOpacity>
              </View>
            </View>
          ))
        )}
      </View>
    );
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
    if (!isEditing && user?.trial_is_expired) {
      Alert.alert(
        "Período de avaliação terminado",
        `Seu período de avaliação terminou.\n\nVocê já gerou:\n* ${user.trial_stats?.proposals_count ?? 0} propostas\n* ${user.trial_stats?.clients_count ?? 0} clientes\n* ${user.trial_stats?.negotiations_count ?? 0} negociações\n\nAssine o Plano Pro para continuar utilizando.`
      );
      return;
    }

    if (!clientName || !doc || !phone || !deadline) {
      Alert.alert("Atenção", "Preencha cliente, CNPJ/CPF, telefone e prazo.");
      return;
    }

    const cleanProducts = products.map((p) => {
      if (p.product_id) {
        return {
          product_id: p.product_id,
          name: p.name.trim(),
          description: p.description || "",
          unit: p.unit || "UN",
          unit_price: parseCurrency(p.price),
          quantity: parseNumber(p.quantity),
        };
      } else {
        return {
          name: p.name,
          description: p.description || "",
          unit: p.unit || "UN",
          unit_price: parseCurrency(p.price),
          quantity: parseNumber(p.quantity),
        };
      }
    });
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
        client_email: clientEmail.trim(),
        client_company: clientCompany.trim(),
        client_city: clientCity.trim(),
        client_state: clientState.trim(),
        client_address: clientAddress.trim(),
        client_id: clientId.trim(),
        products: cleanProducts,
        shipping_deadline: deadline.trim(),
        notes: notes.trim(),
        discount: discountNum,
        payment_terms: paymentTerms.trim(),
        images,
        validity_days: parseInt(validity || "15", 10) || 15,
        shipping_type: shippingType.trim(),
        shipping_responsible: shippingResponsible.trim(),
        shipping_company: shippingCompany.trim(),
        manufacturing_days: manufacturingDays.trim(),
        delivery_days: deliveryDays.trim(),
        warranty: warranty.trim(),
        delivery_place: deliveryPlace.trim(),
        incoterm: incoterm.trim(),
        currency,
        commercial_conditions: commercialConditions.trim(),
        internal_notes: internalNotes.trim(),
      };
      console.log("PAYLOAD", payload);
      let response;
      if (isEditing && editId) {
        response = await api.put(`/proposals/${editId}`, payload);
      } else {
        response = await api.post("/proposals", payload);
      }

      reset();
      router.replace(`/proposal/${response.data.id}`);
    } catch (e: any) {
      if (e?.response?.status === 402) {
        setUpgradeMsg(e.response.data?.detail);
        setUpgradeOpen(true);
      } else if (e?.response?.status === 403) {
        Alert.alert(
          "Período de avaliação terminado",
          e.response.data?.detail || "Seu período de avaliação terminou. Assine o Plano Pro para continuar utilizando."
        );
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

                    <Input
                      label="E-mail"
                      value={clientEmail}
                      onChangeText={setClientEmail}
                      placeholder="Ex: cliente@email.com"
                      keyboardType="email-address"
                    />

                    <Input
                      label="Empresa"
                      value={clientCompany}
                      onChangeText={setClientCompany}
                      placeholder="Ex: ACME Ltda"
                    />

                    <View style={{ flexDirection: "row", gap: 8 }}>
                      <View style={{ flex: 2 }}>
                        <Input
                          label="Cidade"
                          value={clientCity}
                          onChangeText={setClientCity}
                          placeholder="Ex: São Paulo"
                        />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Input
                          label="Estado"
                          value={clientState}
                          onChangeText={setClientState}
                          placeholder="Ex: SP"
                        />
                      </View>
                    </View>

                    <Input
                      label="Endereço"
                      value={clientAddress}
                      onChangeText={setClientAddress}
                      placeholder="Ex: Av. Paulista, 1000"
                    />
                  </Section>
                </View>

                                <View style={s.panelCard}>
                  <Section title="Itens">
                    {renderItemsSection()}
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
                    {templates.length > 0 && (
                      <View style={{ gap: 6, marginBottom: 12 }}>
                        <Text style={{ fontSize: 14, fontWeight: "600", color: theme.colors.textSec }}>Aplicar Modelo Comercial:</Text>
                        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
                          {templates.map((tpl) => (
                            <TouchableOpacity
                              key={tpl.id}
                              style={{
                                paddingHorizontal: 12,
                                paddingVertical: 6,
                                borderRadius: 16,
                                borderWidth: 1,
                                borderColor: theme.colors.primary,
                                backgroundColor: theme.colors.statusOpenBg,
                              }}
                              onPress={() => applyTemplate(tpl)}
                              testID={`btn-apply-tpl-desktop-${tpl.id}`}
                            >
                              <Text style={{ fontSize: 12, fontWeight: '700', color: theme.colors.primary }}>
                                {tpl.name}
                              </Text>
                            </TouchableOpacity>
                          ))}
                        </ScrollView>
                      </View>
                    )}

                    <Input
                      label="Prazo de embarque *"
                      value={deadline}
                      onChangeText={setDeadline}
                      placeholder="Ex: 15 dias Úteis"
                    />

                    <View style={{ flexDirection: "row", gap: 8, zIndex: 10 }}>
                      <View style={{ flex: 1 }}>
                        <View style={{ gap: 6 }}>
                          <Text style={{ fontSize: 14, fontWeight: "600", color: theme.colors.textSec }}>Moeda</Text>
                          <View style={{ flexDirection: 'row', gap: 4 }}>
                            {["BRL", "USD", "EUR", "PYG"].map((cur) => (
                              <TouchableOpacity
                                key={cur}
                                style={{
                                  flex: 1,
                                  height: 48,
                                  borderRadius: 8,
                                  borderWidth: 1,
                                  borderColor: currency === cur ? theme.colors.primary : theme.colors.border,
                                  backgroundColor: currency === cur ? theme.colors.statusOpenBg : '#fff',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                }}
                                onPress={() => setCurrency(cur)}
                                testID={`currency-btn-desktop-${cur}`}
                              >
                                <Text style={{ fontSize: 12, fontWeight: '700', color: currency === cur ? theme.colors.primary : theme.colors.text }}>
                                  {cur}
                                </Text>
                              </TouchableOpacity>
                            ))}
                          </View>
                        </View>
                      </View>
                      <View style={{ flex: 1 }}>
                        <Select
                          label="Incoterm"
                          value={incoterm}
                          onValueChange={setIncoterm}
                          options={[
                            { label: "Nenhum", value: "" },
                            { label: "CIF", value: "CIF" },
                            { label: "FOB", value: "FOB" },
                            { label: "EXW", value: "EXW" },
                            { label: "DDP", value: "DDP" },
                            { label: "FAS", value: "FAS" },
                            { label: "CFR", value: "CFR" },
                            { label: "CPT", value: "CPT" },
                            { label: "CIP", value: "CIP" },
                            { label: "DAP", value: "DAP" },
                            { label: "DPU", value: "DPU" },
                          ]}
                          testID="sel-incoterm-desktop"
                        />
                      </View>
                    </View>

                    <View style={{ flexDirection: "row", gap: 8, zIndex: 5 }}>
                      <View style={{ flex: 1 }}>
                        <Select
                          label="Frete"
                          value={shippingType}
                          onValueChange={setShippingType}
                          options={[
                            { label: "Selecione...", value: "" },
                            { label: "CIF", value: "CIF" },
                            { label: "FOB", value: "FOB" },
                            { label: "Por conta do cliente", value: "Por conta do cliente" },
                            { label: "Retirada no local", value: "Retirada no local" },
                            { label: "A combinar", value: "A combinar" },
                          ]}
                          testID="sel-shipping-type-desktop"
                        />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Select
                          label="Condições de pagamento"
                          value={paymentTerms}
                          onValueChange={setPaymentTerms}
                          options={[
                            { label: "Selecione...", value: "" },
                            { label: "À vista", value: "À vista" },
                            { label: "7 dias", value: "7 dias" },
                            { label: "14 dias", value: "14 dias" },
                            { label: "21 dias", value: "21 dias" },
                            { label: "28 dias", value: "28 dias" },
                            { label: "30 dias", value: "30 dias" },
                            { label: "45 dias", value: "45 dias" },
                            { label: "60 dias", value: "60 dias" },
                            { label: "90 dias", value: "90 dias" },
                            { label: "Parcelado", value: "Parcelado" },
                            { label: "Personalizado", value: "Personalizado" },
                          ]}
                          testID="sel-payment-terms-desktop"
                        />
                      </View>
                    </View>

                    <View style={{ flexDirection: "row", gap: 8 }}>
                      <View style={{ flex: 1 }}>
                        <Input
                          label="Responsável pelo frete"
                          value={shippingResponsible}
                          onChangeText={setShippingResponsible}
                          placeholder="Ex: Destinatário"
                          testID="inp-shipping-resp-desktop"
                        />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Input
                          label="Transportadora"
                          value={shippingCompany}
                          onChangeText={setShippingCompany}
                          placeholder="Ex: Alfa Transportes"
                          testID="inp-shipping-comp-desktop"
                        />
                      </View>
                    </View>

                    <View style={{ flexDirection: "row", gap: 8 }}>
                      <View style={{ flex: 1 }}>
                        <Input
                          label="Prazo de fabricação"
                          value={manufacturingDays}
                          onChangeText={setManufacturingDays}
                          placeholder="Ex: 10 dias"
                          testID="inp-manufacturing-desktop"
                        />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Input
                          label="Prazo de entrega"
                          value={deliveryDays}
                          onChangeText={setDeliveryDays}
                          placeholder="Ex: 5 dias"
                          testID="inp-delivery-desktop"
                        />
                      </View>
                    </View>

                    <View style={{ flexDirection: "row", gap: 8 }}>
                      <View style={{ flex: 1 }}>
                        <Input
                          label="Garantia"
                          value={warranty}
                          onChangeText={setWarranty}
                          placeholder="Ex: 12 meses"
                          testID="inp-warranty-desktop"
                        />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Input
                          label="Local de entrega"
                          value={deliveryPlace}
                          onChangeText={setDeliveryPlace}
                          placeholder="Ex: Filial São Paulo"
                          testID="inp-delivery-place-desktop"
                        />
                      </View>
                    </View>

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

                    <Input
                      label="Observações comerciais"
                      value={commercialConditions}
                      onChangeText={setCommercialConditions}
                      placeholder="Ex: Desconto condicionado à quantidade..."
                      multiline
                      testID="inp-commercial-conditions-desktop"
                    />

                    <Input
                      label="Observações internas"
                      value={internalNotes}
                      onChangeText={setInternalNotes}
                      placeholder="Ex: Margem mínima aceitável de 25%..."
                      multiline
                      testID="inp-internal-notes-desktop"
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

                <Input
                  label="E-mail"
                  value={clientEmail}
                  onChangeText={setClientEmail}
                  placeholder="Ex: cliente@email.com"
                  keyboardType="email-address"
                />

                <Input
                  label="Empresa"
                  value={clientCompany}
                  onChangeText={setClientCompany}
                  placeholder="Ex: ACME Ltda"
                />

                <View style={{ flexDirection: "row", gap: 8 }}>
                  <View style={{ flex: 2 }}>
                    <Input
                      label="Cidade"
                      value={clientCity}
                      onChangeText={setClientCity}
                      placeholder="Ex: São Paulo"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Input
                      label="Estado"
                      value={clientState}
                      onChangeText={setClientState}
                      placeholder="Ex: SP"
                    />
                  </View>
                </View>

                <Input
                  label="Endereço"
                  value={clientAddress}
                  onChangeText={setClientAddress}
                  placeholder="Ex: Av. Paulista, 1000"
                />
              </Section>

                            <Section title="Itens">
                {renderItemsSection()}
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
                {templates.length > 0 && (
                  <View style={{ gap: 6, marginBottom: 12 }}>
                    <Text style={{ fontSize: 14, fontWeight: "600", color: theme.colors.textSec }}>Aplicar Modelo Comercial:</Text>
                    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
                      {templates.map((tpl) => (
                        <TouchableOpacity
                          key={tpl.id}
                          style={{
                            paddingHorizontal: 12,
                            paddingVertical: 6,
                            borderRadius: 16,
                            borderWidth: 1,
                            borderColor: theme.colors.primary,
                            backgroundColor: theme.colors.statusOpenBg,
                          }}
                          onPress={() => applyTemplate(tpl)}
                          testID={`btn-apply-tpl-mobile-${tpl.id}`}
                        >
                          <Text style={{ fontSize: 12, fontWeight: '700', color: theme.colors.primary }}>
                            {tpl.name}
                          </Text>
                        </TouchableOpacity>
                      ))}
                    </ScrollView>
                  </View>
                )}

                <Input
                  label="Prazo de embarque *"
                  value={deadline}
                  onChangeText={setDeadline}
                  placeholder="Ex: 15 dias úteis"
                />

                <View style={{ flexDirection: "row", gap: 8, zIndex: 10 }}>
                  <View style={{ flex: 1 }}>
                    <View style={{ gap: 6 }}>
                      <Text style={{ fontSize: 14, fontWeight: "600", color: theme.colors.textSec }}>Moeda</Text>
                      <View style={{ flexDirection: 'row', gap: 4 }}>
                        {["BRL", "USD", "EUR", "PYG"].map((cur) => (
                          <TouchableOpacity
                            key={cur}
                            style={{
                              flex: 1,
                              height: 48,
                              borderRadius: 8,
                              borderWidth: 1,
                              borderColor: currency === cur ? theme.colors.primary : theme.colors.border,
                              backgroundColor: currency === cur ? theme.colors.statusOpenBg : '#fff',
                              alignItems: 'center',
                              justifyContent: 'center',
                            }}
                            onPress={() => setCurrency(cur)}
                            testID={`currency-btn-mobile-${cur}`}
                          >
                            <Text style={{ fontSize: 12, fontWeight: '700', color: currency === cur ? theme.colors.primary : theme.colors.text }}>
                              {cur}
                            </Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    </View>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Select
                      label="Incoterm"
                      value={incoterm}
                      onValueChange={setIncoterm}
                      options={[
                        { label: "Nenhum", value: "" },
                        { label: "CIF", value: "CIF" },
                        { label: "FOB", value: "FOB" },
                        { label: "EXW", value: "EXW" },
                        { label: "DDP", value: "DDP" },
                        { label: "FAS", value: "FAS" },
                        { label: "CFR", value: "CFR" },
                        { label: "CPT", value: "CPT" },
                        { label: "CIP", value: "CIP" },
                        { label: "DAP", value: "DAP" },
                        { label: "DPU", value: "DPU" },
                      ]}
                      testID="sel-incoterm-mobile"
                    />
                  </View>
                </View>

                <View style={{ flexDirection: "row", gap: 8, zIndex: 5 }}>
                  <View style={{ flex: 1 }}>
                    <Select
                      label="Frete"
                      value={shippingType}
                      onValueChange={setShippingType}
                      options={[
                        { label: "Selecione...", value: "" },
                        { label: "CIF", value: "CIF" },
                        { label: "FOB", value: "FOB" },
                        { label: "Por conta do cliente", value: "Por conta do cliente" },
                        { label: "Retirada no local", value: "Retirada no local" },
                        { label: "A combinar", value: "A combinar" },
                      ]}
                      testID="sel-shipping-type-mobile"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Select
                      label="Condições de pagamento"
                      value={paymentTerms}
                      onValueChange={setPaymentTerms}
                      options={[
                        { label: "Selecione...", value: "" },
                        { label: "À vista", value: "À vista" },
                        { label: "7 dias", value: "7 dias" },
                        { label: "14 dias", value: "14 dias" },
                        { label: "21 dias", value: "21 dias" },
                        { label: "28 dias", value: "28 dias" },
                        { label: "30 dias", value: "30 dias" },
                        { label: "45 dias", value: "45 dias" },
                        { label: "60 dias", value: "60 dias" },
                        { label: "90 dias", value: "90 dias" },
                        { label: "Parcelado", value: "Parcelado" },
                        { label: "Personalizado", value: "Personalizado" },
                      ]}
                      testID="sel-payment-terms-mobile"
                    />
                  </View>
                </View>

                <View style={{ flexDirection: "row", gap: 8 }}>
                  <View style={{ flex: 1 }}>
                    <Input
                      label="Responsável pelo frete"
                      value={shippingResponsible}
                      onChangeText={setShippingResponsible}
                      placeholder="Ex: Destinatário"
                      testID="inp-shipping-resp-mobile"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Input
                      label="Transportadora"
                      value={shippingCompany}
                      onChangeText={setShippingCompany}
                      placeholder="Ex: Alfa Transportes"
                      testID="inp-shipping-comp-mobile"
                    />
                  </View>
                </View>

                <View style={{ flexDirection: "row", gap: 8 }}>
                  <View style={{ flex: 1 }}>
                    <Input
                      label="Prazo de fabricação"
                      value={manufacturingDays}
                      onChangeText={setManufacturingDays}
                      placeholder="Ex: 10 dias"
                      testID="inp-manufacturing-mobile"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Input
                      label="Prazo de entrega"
                      value={deliveryDays}
                      onChangeText={setDeliveryDays}
                      placeholder="Ex: 5 dias"
                      testID="inp-delivery-mobile"
                    />
                  </View>
                </View>

                <View style={{ flexDirection: "row", gap: 8 }}>
                  <View style={{ flex: 1 }}>
                    <Input
                      label="Garantia"
                      value={warranty}
                      onChangeText={setWarranty}
                      placeholder="Ex: 12 meses"
                      testID="inp-warranty-mobile"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Input
                      label="Local de entrega"
                      value={deliveryPlace}
                      onChangeText={setDeliveryPlace}
                      placeholder="Ex: Filial São Paulo"
                      testID="inp-delivery-place-mobile"
                    />
                  </View>
                </View>

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

                <Input
                  label="Observações comerciais"
                  value={commercialConditions}
                  onChangeText={setCommercialConditions}
                  placeholder="Ex: Desconto condicionado à quantidade..."
                  multiline
                  testID="inp-commercial-conditions-mobile"
                />

                <Input
                  label="Observações internas"
                  value={internalNotes}
                  onChangeText={setInternalNotes}
                  placeholder="Ex: Margem mínima aceitável de 25%..."
                  multiline
                  testID="inp-internal-notes-mobile"
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



function Select({ label, value, onValueChange, options, testID }: any) {
  const [open, setOpen] = useState(false);
  return (
    <View style={{ gap: 6, position: 'relative', zIndex: open ? 999 : 1 }}>
      <Text style={{ fontSize: 14, fontWeight: "600", color: theme.colors.textSec }}>{label}</Text>
      <TouchableOpacity
        testID={testID}
        style={{
          height: 48,
          borderWidth: 1,
          borderColor: theme.colors.border,
          borderRadius: 8,
          paddingHorizontal: 16,
          backgroundColor: "#fff",
          justifyContent: "center",
        }}
        onPress={() => setOpen(!open)}
      >
        <Text style={{ color: value ? theme.colors.text : theme.colors.textMuted }}>
          {options.find((o: any) => o.value === value)?.label || "Selecione..."}
        </Text>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={16} color={theme.colors.textSec} style={{ position: 'absolute', right: 12, top: 16 }} />
      </TouchableOpacity>
      {open && (
        <View style={{ backgroundColor: '#fff', borderWidth: 1, borderColor: theme.colors.border, borderRadius: 8, marginTop: 4, position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 1000, shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.1, shadowRadius: 4, elevation: 3 }}>
          <ScrollView style={{ maxHeight: 200 }} nestedScrollEnabled={true} keyboardShouldPersistTaps="handled">
            {options.map((opt: any) => (
              <TouchableOpacity
                key={opt.value}
                style={{ padding: 12, borderBottomWidth: 1, borderBottomColor: theme.colors.border }}
                onPress={() => {
                  onValueChange(opt.value);
                  setOpen(false);
                }}
              >
                <Text style={{ color: theme.colors.text, fontWeight: value === opt.value ? '700' : '400' }}>
                  {opt.label}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      )}
    </View>
  );
}

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
    addedProductRow: {
    padding: 12,
    backgroundColor: "#F1F5F9",
    borderRadius: 12,
    marginBottom: 8,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  addedProductTitle: {
    fontSize: 15,
    color: theme.colors.text,
  },
  addedProductDesc: {
    fontSize: 12,
    color: theme.colors.textMuted,
    marginTop: 2,
  },
  addedProductSub: {
    fontSize: 13,
    color: theme.colors.textSec,
    marginTop: 4,
  },
  addedProductTotal: {
    fontSize: 15,
    fontWeight: "700",
    color: theme.colors.text,
  },
  itemEditor: {
    padding: 12,
    backgroundColor: "#F8FAFC",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: theme.colors.primary,
    marginBottom: 8,
    gap: 8,
  },
  catalogLinkNotice: {
    color: theme.colors.primary,
    fontSize: 12,
    fontWeight: "700",
  },
  itemEditorInput: {
    minHeight: 44,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: "#fff",
    color: theme.colors.text,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  itemEditorDescription: {
    minHeight: 68,
    textAlignVertical: "top",
  },
  itemEditorFields: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  itemEditorField: {
    flex: 1,
    minWidth: 120,
  },
  itemEditorActions: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 8,
  },
  itemEditorCancel: {
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  itemEditorCancelText: {
    color: theme.colors.textSec,
    fontWeight: "700",
  },
  itemEditorSave: {
    backgroundColor: theme.colors.primary,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  itemEditorSaveText: {
    color: "#fff",
    fontWeight: "700",
  },
  selectorBox: {
    padding: 14,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 14,
    marginBottom: 16,
    gap: 8,
  },
  selectedProductInfo: {
    padding: 8,
    backgroundColor: "#E2E8F0",
    borderRadius: 8,
    marginTop: 4,
  },
  selectedProductText: {
    fontSize: 13,
    color: theme.colors.text,
    fontWeight: "600",
  },
  addButton: {
    height: 52,
    backgroundColor: theme.colors.primary,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 16,
  },
  addButtonText: {
    color: "#fff",
    fontWeight: "700",
    fontSize: 14,
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
  tabButton: {
    flex: 1,
    height: 40,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: theme.colors.border,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#F8FAFC",
  },
  tabButtonActive: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
  },
  tabButtonText: {
    color: theme.colors.textSec,
    fontWeight: "600",
    fontSize: 12,
  },
  tabButtonTextActive: {
    color: "#fff",
  },
});

